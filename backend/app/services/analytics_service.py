"""
学情分析服务

核心功能：
1. 重算学生知识点掌握度（基于 homework_results）
2. 识别薄弱知识点
3. 针对性出题（基于薄弱点选题）
4. 班级排行 / 整体学情
"""
from collections import defaultdict
from datetime import datetime

from sqlmodel import Session, select

from app.models.analytics import StudentKPStats, WeakPoint
from app.models.homework import HomeworkResult
from app.models.question import Question, QuestionKnowledge
from app.models.student import Student


def recompute_student_stats(session: Session, student_id: int) -> None:
    """
    重算某学生的知识点掌握度

    算法：
    - 遍历该学生所有 homework_result.result_detail
    - 累计每知识点的 attempts / correct / weighted_score
    - 写回 student_kp_stats（upsert）
    """
    # 收集所有 result_detail
    results = session.exec(
        select(HomeworkResult).where(HomeworkResult.student_id == student_id)
    ).all()

    # kp_id → 累计
    kp_total: dict[int, int] = defaultdict(int)
    kp_correct: dict[int, int] = defaultdict(int)
    kp_weighted: dict[int, float] = defaultdict(float)
    kp_last_practiced: dict[int, datetime] = {}

    for r in results:
        if not r.result_detail:
            continue
        for item in r.result_detail:
            score = item.get("score", 0)
            is_correct = item.get("is_correct", False)
            kp_ids = item.get("kp_ids", [])
            recorded_at = r.recorded_at

            for kp_id in kp_ids:
                kp_total[kp_id] += 1
                if is_correct:
                    kp_correct[kp_id] += 1
                kp_weighted[kp_id] += float(score)
                if kp_id not in kp_last_practiced or recorded_at > kp_last_practiced[kp_id]:
                    kp_last_practiced[kp_id] = recorded_at

    # upsert 到 student_kp_stats
    for kp_id, total in kp_total.items():
        correct = kp_correct[kp_id]
        accuracy = correct / total if total > 0 else 0.0
        weighted = kp_weighted[kp_id]

        existing = session.exec(
            select(StudentKPStats)
            .where(StudentKPStats.student_id == student_id)
            .where(StudentKPStats.knowledge_point_id == kp_id)
        ).first()

        if existing:
            existing.total_attempts = total
            existing.correct_count = correct
            existing.accuracy = accuracy
            existing.weighted_score = weighted
            existing.last_practiced_at = kp_last_practiced.get(kp_id)
            existing.last_updated_at = datetime.utcnow()
            session.add(existing)
        else:
            stats = StudentKPStats(
                student_id=student_id,
                knowledge_point_id=kp_id,
                total_attempts=total,
                correct_count=correct,
                accuracy=accuracy,
                weighted_score=weighted,
                last_practiced_at=kp_last_practiced.get(kp_id),
            )
            session.add(stats)

    # 同时识别薄弱点
    _update_weak_points(session, student_id, kp_total, kp_correct)
    session.commit()

    # 更新学生聚合字段
    _update_student_aggregate(session, student_id)


def _update_weak_points(
    session: Session,
    student_id: int,
    kp_total: dict[int, int],
    kp_correct: dict[int, int],
) -> None:
    """根据正确率标记薄弱点"""
    for kp_id, total in kp_total.items():
        correct = kp_correct[kp_id]
        accuracy = correct / total if total > 0 else 0.0

        # 阈值：accuracy < 0.6 且 attempts >= 3 视为薄弱
        if accuracy < 0.6 and total >= 3:
            severity = "high" if accuracy < 0.4 else "medium"

            existing = session.exec(
                select(WeakPoint)
                .where(WeakPoint.student_id == student_id)
                .where(WeakPoint.knowledge_point_id == kp_id)
                .where(WeakPoint.is_resolved == False)
            ).first()

            if existing:
                existing.accuracy = accuracy
                existing.attempts = total
                existing.severity = severity
                existing.recommended_practice_count = min(10, max(3, int((1 - accuracy) * 10)))
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                wp = WeakPoint(
                    student_id=student_id,
                    knowledge_point_id=kp_id,
                    accuracy=accuracy,
                    attempts=total,
                    severity=severity,
                    recommended_practice_count=min(10, max(3, int((1 - accuracy) * 10))),
                )
                session.add(wp)


def _update_student_aggregate(session: Session, student_id: int) -> None:
    """更新学生表的聚合字段"""
    student = session.get(Student, student_id)
    if not student:
        return

    results = session.exec(
        select(HomeworkResult).where(HomeworkResult.student_id == student_id)
    ).all()

    if results:
        total_homework = len(results)
        scores = [r.total_score for r in results if r.total_score is not None]
        avg = sum(scores) / len(scores) if scores else None

        student.total_homework_count = total_homework
        student.average_score = avg
        session.add(student)


def get_student_overview(session: Session, student_id: int) -> dict:
    """学生学情概览"""
    student = session.get(Student, student_id)
    if not student:
        return {"error": "学生不存在"}

    stats = session.exec(
        select(StudentKPStats).where(StudentKPStats.student_id == student_id)
    ).all()

    weak_points = session.exec(
        select(WeakPoint)
        .where(WeakPoint.student_id == student_id)
        .where(WeakPoint.is_resolved == False)
        .order_by(WeakPoint.accuracy)
        .limit(5)
    ).all()

    return {
        "student_id": student_id,
        "name": student.name,
        "average_score": student.average_score,
        "total_homework": student.total_homework_count,
        "knowledge_points_practiced": len(stats),
        "weak_points": [
            {"kp_id": w.knowledge_point_id, "accuracy": w.accuracy, "severity": w.severity}
            for w in weak_points
        ],
    }


def get_student_weak_points(session: Session, student_id: int, top_n: int = 5) -> list[dict]:
    """获取学生薄弱知识点 Top N"""
    weak_points = session.exec(
        select(WeakPoint)
        .where(WeakPoint.student_id == student_id)
        .where(WeakPoint.is_resolved == False)
        .order_by(WeakPoint.accuracy)
        .limit(top_n)
    ).all()

    from app.models.knowledge_point import KnowledgePoint
    result = []
    for wp in weak_points:
        kp = session.get(KnowledgePoint, wp.knowledge_point_id)
        result.append({
            "kp_id": wp.knowledge_point_id,
            "kp_name": kp.name if kp else None,
            "kp_code": kp.code if kp else None,
            "accuracy": wp.accuracy,
            "severity": wp.severity,
            "attempts": wp.attempts,
            "recommended_practice_count": wp.recommended_practice_count,
        })
    return result


def generate_targeted_practice(
    session: Session,
    student_id: int,
    count: int = 5,
    difficulty_min: int = 1,
    difficulty_max: int = 5,
) -> dict:
    """
    基于薄弱知识点选题

    算法：
    1. 取学生薄弱知识点 Top N
    2. 从每个薄弱知识点下选 count/N 道题
    3. 排除最近已做过的题（去重）
    4. 难度匹配
    """
    weak_points = session.exec(
        select(WeakPoint)
        .where(WeakPoint.student_id == student_id)
        .where(WeakPoint.is_resolved == False)
        .order_by(WeakPoint.accuracy)
    ).all()

    if not weak_points:
        return {"questions": [], "message": "该生暂无可识别的薄弱知识点"}

    # 学生已做过的题（最近 20 次作业）
    recent_results = session.exec(
        select(HomeworkResult)
        .where(HomeworkResult.student_id == student_id)
        .order_by(HomeworkResult.recorded_at.desc())
        .limit(20)
    ).all()
    done_question_ids = set()
    for r in recent_results:
        if r.result_detail:
            for item in r.result_detail:
                done_question_ids.add(item.get("question_id"))

    # 按薄弱点选题
    selected: list[Question] = []
    per_kp = max(1, count // len(weak_points))

    for wp in weak_points:
        candidates = session.exec(
            select(Question)
            .join(QuestionKnowledge, QuestionKnowledge.question_id == Question.id)
            .where(QuestionKnowledge.knowledge_point_id == wp.knowledge_point_id)
            .where(Question.is_active == True)
            .where(Question.difficulty >= difficulty_min)
            .where(Question.difficulty <= difficulty_max)
            .where(~Question.id.in_(done_question_ids) if done_question_ids else True)
        ).all()

        import random
        picked = random.sample(candidates, min(per_kp, len(candidates)))
        selected.extend(picked)

        if len(selected) >= count:
            break

    return {
        "questions": [
            {
                "id": q.id,
                "stem": q.stem,
                "question_type": q.question_type,
                "difficulty": q.difficulty,
            }
            for q in selected[:count]
        ],
        "based_on": [wp.knowledge_point_id for wp in weak_points],
        "total": len(selected),
    }


def get_class_ranking(
    session: Session,
    class_id: int,
    homework_id: int | None = None,
) -> list[dict]:
    """班级排行（按作业成绩）"""
    from app.models.class_ import ClassStudent

    student_ids = session.exec(
        select(ClassStudent.student_id).where(ClassStudent.class_id == class_id)
    ).all()

    if not student_ids:
        return []

    stmt = (
        select(HomeworkResult, Student)
        .join(Student, Student.id == HomeworkResult.student_id)
        .where(HomeworkResult.student_id.in_(student_ids))
    )
    if homework_id:
        stmt = stmt.where(HomeworkResult.homework_id == homework_id)

    stmt = stmt.order_by(HomeworkResult.total_score.desc())

    rows = session.exec(stmt).all()
    return [
        {
            "rank": idx + 1,
            "student_id": s.id,
            "name": s.name,
            "student_no": s.student_no,
            "total_score": r.total_score,
            "max_score": r.max_score,
            "percentage": r.percentage,
        }
        for idx, (r, s) in enumerate(rows)
    ]


def get_class_overview(session: Session, class_id: int) -> dict:
    """班级整体学情"""
    from app.models.class_ import ClassStudent

    student_ids = session.exec(
        select(ClassStudent.student_id).where(ClassStudent.class_id == class_id)
    ).all()

    if not student_ids:
        return {"student_count": 0}

    # 整体平均分
    results = session.exec(
        select(HomeworkResult).where(HomeworkResult.student_id.in_(student_ids))
    ).all()

    scores = [r.total_score for r in results if r.total_score is not None]

    return {
        "class_id": class_id,
        "student_count": len(student_ids),
        "total_homework": len(results),
        "avg_score": sum(scores) / len(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "min_score": min(scores) if scores else None,
    }
