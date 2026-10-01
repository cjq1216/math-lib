"""学情分析服务：基于每题明细与知识点快照的掌握度聚合、趋势计算、薄弱点自动标记/解除与针对性出题。"""

import random
from collections import defaultdict
from datetime import datetime

from sqlmodel import Session, select

from app.models.analytics import StudentKPStats, WeakPoint
from app.models.class_ import ClassStudent
from app.models.homework import HomeworkQuestionResult, HomeworkResult
from app.models.knowledge_point import KnowledgePoint
from app.models.question import Question, QuestionKnowledge
from app.models.student import Student


def recompute_student_stats(session: Session, student_id: int) -> None:
    """
    重算某学生的知识点掌握度、趋势与薄弱点闭环：
    1. 优先从 HomeworkQuestionResult 关联真实题库知识点 QuestionKnowledge（不信任客户端任意输入）；
    2. 计算累计正确率、最近 5 次正确率与趋势（up/down/stable）；
    3. 自动识别薄弱点，并在正确率提升后自动解除（is_resolved = True）；
    4. 刷新 student 表的作业总次数与平均分。
    """
    # 1. 查找学生所有的作业结果（按记录时间正序排序）
    homework_results = session.exec(
        select(HomeworkResult)
        .where(HomeworkResult.student_id == student_id)
        .order_by(HomeworkResult.recorded_at.asc())
    ).all()

    hr_ids = [hr.id for hr in homework_results if hr.id is not None]
    hr_date_map = {hr.id: hr.recorded_at for hr in homework_results}

    # 2. 收集每道题的作答结果与对应的知识点
    # kp_id -> 升序作答历史：[{"is_correct": bool, "score": float, "recorded_at": datetime}, ...]
    kp_attempts: dict[int, list[dict]] = defaultdict(list)

    if hr_ids:
        # 查询正规明细表
        q_results = session.exec(
            select(HomeworkQuestionResult)
            .where(HomeworkQuestionResult.homework_result_id.in_(hr_ids))
            .order_by(HomeworkQuestionResult.recorded_at.asc())
        ).all()

        if q_results:
            q_ids = list({qr.question_id for qr in q_results})
            qk_rows = session.exec(
                select(QuestionKnowledge).where(QuestionKnowledge.question_id.in_(q_ids))
            ).all()
            q_to_kps: dict[int, list[int]] = defaultdict(list)
            for qk in qk_rows:
                q_to_kps[qk.question_id].append(qk.knowledge_point_id)

            for qr in q_results:
                kps = q_to_kps.get(qr.question_id, [])
                rec_at = qr.recorded_at or hr_date_map.get(qr.homework_result_id, datetime.utcnow())
                # 若题目绑定多个知识点，分摊分值
                weight = 1.0 / len(kps) if kps else 1.0
                for kp_id in kps:
                    kp_attempts[kp_id].append(
                        {
                            "is_correct": qr.is_correct,
                            "score": qr.score * weight,
                            "recorded_at": rec_at,
                        }
                    )

    # 回退兼容：若某些作业只有 result_detail JSON
    for hr in homework_results:
        # 如果已经通过 HomeworkQuestionResult 处理了该作业，则跳过
        if hr.result_detail and not session.exec(
            select(HomeworkQuestionResult.id).where(HomeworkQuestionResult.homework_result_id == hr.id)
        ).first():
            for item in hr.result_detail:
                score = float(item.get("score", 0))
                is_correct = bool(item.get("is_correct", False))
                q_id = item.get("question_id")
                kp_ids = item.get("kp_ids") or []
                if q_id and not kp_ids:
                    qk_rows = session.exec(
                        select(QuestionKnowledge.knowledge_point_id).where(QuestionKnowledge.question_id == q_id)
                    ).all()
                    kp_ids = list(qk_rows)

                weight = 1.0 / len(kp_ids) if kp_ids else 1.0
                for kp_id in kp_ids:
                    kp_attempts[kp_id].append(
                        {
                            "is_correct": is_correct,
                            "score": score * weight,
                            "recorded_at": hr.recorded_at,
                        }
                    )

    # 3. 计算每个知识点的累计指标、最近 5 次与趋势
    for kp_id, attempts in kp_attempts.items():
        total = len(attempts)
        if total == 0:
            continue
        correct = sum(1 for a in attempts if a["is_correct"])
        accuracy = correct / total
        weighted_score = sum(a["score"] for a in attempts)
        last_practiced = max(a["recorded_at"] for a in attempts)

        # 最近 5 次正确率与趋势计算
        recent_5 = attempts[-5:]
        recent_5_acc = sum(1 for a in recent_5 if a["is_correct"]) / len(recent_5)

        # 趋势判定：对比后半段与前半段表现，或最近作答表现
        if total < 3:
            trend = "stable"
        else:
            half = max(1, total // 2)
            earlier_acc = sum(1 for a in attempts[:half] if a["is_correct"]) / half
            later_acc = sum(1 for a in attempts[half:] if a["is_correct"]) / (total - half)
            diff = later_acc - earlier_acc
            if diff >= 0.1:
                trend = "up"
            elif diff <= -0.1:
                trend = "down"
            else:
                trend = "stable"

        # upsert 到 StudentKPStats
        stats = session.exec(
            select(StudentKPStats)
            .where(StudentKPStats.student_id == student_id)
            .where(StudentKPStats.knowledge_point_id == kp_id)
        ).first()

        if stats is None:
            stats = StudentKPStats(
                student_id=student_id,
                knowledge_point_id=kp_id,
            )

        stats.total_attempts = total
        stats.correct_count = correct
        stats.accuracy = accuracy
        stats.weighted_score = weighted_score
        stats.recent_5_accuracy = recent_5_acc
        stats.trend = trend
        stats.last_practiced_at = last_practiced
        stats.last_updated_at = datetime.utcnow()
        session.add(stats)

    # 4. 自动标记薄弱点与自动解除（闭环）
    _update_weak_points_lifecycle(session, student_id, kp_attempts)

    # 5. 更新学生汇总字段
    _update_student_aggregate(session, student_id)
    session.flush()


def _update_weak_points_lifecycle(
    session: Session,
    student_id: int,
    kp_attempts: dict[int, list[dict]],
) -> None:
    """
    薄弱点生命周期管理：
    - 触发标记：attempts >= 3 且 accuracy < 0.6（accuracy < 0.4 为 high，否则 medium）
    - 触发解除：attempts >= 3 且 accuracy >= 0.6，或最近作答连续合格（recent_5_acc >= 0.8）
    """
    for kp_id, attempts in kp_attempts.items():
        total = len(attempts)
        if total < 3:
            continue

        correct = sum(1 for a in attempts if a["is_correct"])
        accuracy = correct / total
        recent_5 = attempts[-5:]
        recent_5_acc = sum(1 for a in recent_5 if a["is_correct"]) / len(recent_5)

        existing_wp = session.exec(
            select(WeakPoint)
            .where(WeakPoint.student_id == student_id)
            .where(WeakPoint.knowledge_point_id == kp_id)
        ).first()

        # 计算最近连续正确次数
        consecutive_correct = 0
        for a in reversed(attempts):
            if a["is_correct"]:
                consecutive_correct += 1
            else:
                break

        # 解除标准：累计正确率 >= 60%，或后续连续做对 >= 2 次，或最近5次正确率 >= 80%
        is_remedied = accuracy >= 0.6 or consecutive_correct >= 2 or recent_5_acc >= 0.8

        if is_remedied:
            if existing_wp and not existing_wp.is_resolved:
                existing_wp.is_resolved = True
                existing_wp.resolved_at = datetime.utcnow()
                existing_wp.accuracy = accuracy
                existing_wp.attempts = total
                existing_wp.updated_at = datetime.utcnow()
                session.add(existing_wp)
        elif accuracy < 0.6:
            # 触发或保持薄弱点标记
            severity = "high" if accuracy < 0.4 else "medium"
            rec_count = min(10, max(3, int((1 - accuracy) * 10)))

            if existing_wp:
                existing_wp.accuracy = accuracy
                existing_wp.attempts = total
                existing_wp.severity = severity
                existing_wp.recommended_practice_count = rec_count
                existing_wp.is_resolved = False
                existing_wp.resolved_at = None
                existing_wp.updated_at = datetime.utcnow()
                session.add(existing_wp)
            else:
                wp = WeakPoint(
                    student_id=student_id,
                    knowledge_point_id=kp_id,
                    accuracy=accuracy,
                    attempts=total,
                    severity=severity,
                    recommended_practice_count=rec_count,
                    is_resolved=False,
                )
                session.add(wp)


def _update_student_aggregate(session: Session, student_id: int) -> None:
    """更新学生表的累计作业数与平均分。"""
    student = session.get(Student, student_id)
    if not student:
        return

    results = session.exec(
        select(HomeworkResult).where(HomeworkResult.student_id == student_id)
    ).all()

    if results:
        student.total_homework_count = len(results)
        scores = [r.total_score for r in results if r.total_score is not None]
        student.average_score = (sum(scores) / len(scores)) if scores else None
    else:
        student.total_homework_count = 0
        student.average_score = None
    session.add(student)


def get_student_overview(session: Session, student_id: int) -> dict:
    """学生学情概览。"""
    student = session.get(Student, student_id)
    if not student:
        return {"error": "学生不存在"}

    stats = session.exec(
        select(StudentKPStats).where(StudentKPStats.student_id == student_id)
    ).all()

    # 仅展示未攻克的活跃薄弱点
    active_weak_points = session.exec(
        select(WeakPoint)
        .where(WeakPoint.student_id == student_id)
        .where(WeakPoint.is_resolved.is_(False))
        .order_by(WeakPoint.accuracy.asc())
        .limit(5)
    ).all()

    kp_ids = [w.knowledge_point_id for w in active_weak_points]
    kp_stats_map = {s.knowledge_point_id: s for s in stats if s.knowledge_point_id in kp_ids}

    return {
        "student_id": student_id,
        "name": student.name,
        "average_score": student.average_score,
        "total_homework": student.total_homework_count,
        "knowledge_points_practiced": len(stats),
        "weak_points": [
            {
                "kp_id": w.knowledge_point_id,
                "accuracy": w.accuracy,
                "severity": w.severity,
                "trend": kp_stats_map.get(w.knowledge_point_id).trend if kp_stats_map.get(w.knowledge_point_id) else None,
                "recent_5_accuracy": kp_stats_map.get(w.knowledge_point_id).recent_5_accuracy if kp_stats_map.get(w.knowledge_point_id) else None,
            }
            for w in active_weak_points
        ],
    }


def get_student_weak_points(session: Session, student_id: int, top_n: int = 5) -> list[dict]:
    """获取学生薄弱知识点列表（包含已攻克标记与趋势）。"""
    weak_points = session.exec(
        select(WeakPoint)
        .where(WeakPoint.student_id == student_id)
        .order_by(WeakPoint.is_resolved.asc(), WeakPoint.accuracy.asc())
        .limit(top_n)
    ).all()

    stats_map = {
        s.knowledge_point_id: s
        for s in session.exec(
            select(StudentKPStats).where(StudentKPStats.student_id == student_id)
        ).all()
    }

    result = []
    for wp in weak_points:
        kp = session.get(KnowledgePoint, wp.knowledge_point_id)
        st = stats_map.get(wp.knowledge_point_id)
        result.append(
            {
                "kp_id": wp.knowledge_point_id,
                "kp_name": kp.name if kp else None,
                "kp_code": kp.code if kp else None,
                "accuracy": wp.accuracy,
                "severity": wp.severity,
                "attempts": wp.attempts,
                "recommended_practice_count": wp.recommended_practice_count,
                "trend": st.trend if st else None,
                "recent_5_accuracy": st.recent_5_accuracy if st else None,
                "is_resolved": wp.is_resolved,
                "resolved_at": wp.resolved_at,
            }
        )
    return result


def generate_targeted_practice(
    session: Session,
    student_id: int,
    count: int = 5,
    difficulty_min: int = 1,
    difficulty_max: int = 5,
) -> dict:
    """
    基于薄弱知识点选题并严格去重：
    1. 取学生未攻克的活跃薄弱知识点 Top N；
    2. 严格排除该学生已作答过的所有题目（通过 HomeworkQuestionResult 查重）；
    3. 确保薄弱点题目命中率 >= 80%（PRD 验收要求）；
    4. 难度区间严格过滤。
    """
    active_weak_points = session.exec(
        select(WeakPoint)
        .where(WeakPoint.student_id == student_id)
        .where(WeakPoint.is_resolved.is_(False))
        .order_by(WeakPoint.accuracy.asc())
    ).all()

    if not active_weak_points:
        return {"questions": [], "message": "该生暂无可识别的未攻克薄弱知识点"}

    weak_kp_ids = [wp.knowledge_point_id for wp in active_weak_points]

    # 查询该学生所有已作答过的 question_id
    hr_ids = session.exec(
        select(HomeworkResult.id).where(HomeworkResult.student_id == student_id)
    ).all()
    done_question_ids: set[int] = set()
    if hr_ids:
        qr_qids = session.exec(
            select(HomeworkQuestionResult.question_id).where(
                HomeworkQuestionResult.homework_result_id.in_(hr_ids)
            )
        ).all()
        done_question_ids.update(qr_qids)

    # 1. 优先从薄弱知识点中选出未做过的新题
    weak_candidates = session.exec(
        select(Question)
        .join(QuestionKnowledge, QuestionKnowledge.question_id == Question.id)
        .where(QuestionKnowledge.knowledge_point_id.in_(weak_kp_ids))
        .where(Question.is_active.is_(True))
        .where(Question.difficulty >= difficulty_min)
        .where(Question.difficulty <= difficulty_max)
        .where(~Question.id.in_(done_question_ids) if done_question_ids else True)
    ).all()

    # 去重（因为一题可能关联多个薄弱点）
    unique_weak_map = {q.id: q for q in weak_candidates}
    unique_weak_list = list(unique_weak_map.values())

    # 洗牌随机选取
    random.shuffle(unique_weak_list)
    selected: list[Question] = unique_weak_list[:count]

    # 2. 如果薄弱点题量不足，且需要补足题量，在保证薄弱点命中率 >= 80% 的前提下补充其他未做过的题目
    if len(selected) < count:
        target_weak_count = int(count * 0.8)
        # 如果当前薄弱点题目已经达到或不足但只能全选，看是否补充其他题
        needed = count - len(selected)
        already_selected_ids = {q.id for q in selected}
        all_excluded_ids = done_question_ids | already_selected_ids

        supplemental_candidates = session.exec(
            select(Question)
            .where(Question.is_active.is_(True))
            .where(Question.difficulty >= difficulty_min)
            .where(Question.difficulty <= difficulty_max)
            .where(~Question.id.in_(all_excluded_ids) if all_excluded_ids else True)
            .limit(needed * 3)
        ).all()

        supp_list = list(supplemental_candidates)
        random.shuffle(supp_list)
        # 补充题目，但不破坏薄弱点命中率 >= 80% 的规则（除非薄弱点总题库实在不够）
        max_supp = max(0, count - max(target_weak_count, len(selected)))
        selected.extend(supp_list[:max_supp])

    return {
        "questions": [
            {
                "id": q.id,
                "stem": q.stem,
                "question_type": q.question_type,
                "difficulty": q.difficulty,
            }
            for q in selected
        ],
        "based_on": weak_kp_ids,
        "total": len(selected),
    }


def get_class_ranking(
    session: Session,
    class_id: int,
    homework_id: int | None = None,
) -> list[dict]:
    """
    班级学生成绩排行：
    - 若指定 homework_id：按单次作业得分降序排序；
    - 若未指定 homework_id：按学生综合平均得分降序排序，一人一行。
    """
    # 获取班级在读学生名单
    active_students = session.exec(
        select(Student)
        .join(ClassStudent, ClassStudent.student_id == Student.id)
        .where(
            ClassStudent.class_id == class_id,
            ClassStudent.left_at.is_(None),
        )
    ).all()

    if not active_students:
        return []

    st_map = {s.id: s for s in active_students}
    student_ids = list(st_map.keys())

    if homework_id:
        # 指定单次作业排行
        results = session.exec(
            select(HomeworkResult)
            .where(
                HomeworkResult.homework_id == homework_id,
                HomeworkResult.student_id.in_(student_ids),
            )
            .order_by(HomeworkResult.total_score.desc())
        ).all()

        ranked = []
        for idx, r in enumerate(results):
            s = st_map.get(r.student_id)
            if s:
                ranked.append(
                    {
                        "rank": idx + 1,
                        "student_id": s.id,
                        "name": s.name,
                        "student_no": s.student_no,
                        "total_score": r.total_score,
                        "max_score": r.max_score,
                        "percentage": r.percentage,
                    }
                )
        return ranked
    else:
        # 班级综合平均分排行
        # 聚合每个学生的全部作业成绩
        all_results = session.exec(
            select(HomeworkResult).where(HomeworkResult.student_id.in_(student_ids))
        ).all()

        student_scores: dict[int, list[float]] = defaultdict(list)
        for r in all_results:
            if r.percentage is not None:
                student_scores[r.student_id].append(r.percentage)

        student_avg = []
        for s in active_students:
            scores = student_scores.get(s.id, [])
            avg_pct = (sum(scores) / len(scores)) if scores else None
            student_avg.append((s, avg_pct))

        # 按平均百分比降序排序（未有成绩的排最后）
        student_avg.sort(key=lambda x: (x[1] is not None, x[1] or 0), reverse=True)

        return [
            {
                "rank": idx + 1,
                "student_id": s.id,
                "name": s.name,
                "student_no": s.student_no,
                "total_score": round(avg_pct, 1) if avg_pct is not None else None,
                "max_score": 100.0,
                "percentage": round(avg_pct, 1) if avg_pct is not None else None,
            }
            for idx, (s, avg_pct) in enumerate(student_avg)
        ]


def get_class_overview(session: Session, class_id: int) -> dict:
    """班级整体学情统计：学生人数、作业总数、平均分、最高分、最低分。"""
    active_students = session.exec(
        select(Student.id)
        .join(ClassStudent, ClassStudent.student_id == Student.id)
        .where(
            ClassStudent.class_id == class_id,
            ClassStudent.left_at.is_(None),
        )
    ).all()

    student_count = len(active_students)
    if student_count == 0:
        return {
            "class_id": class_id,
            "student_count": 0,
            "total_homework": 0,
            "avg_score": None,
            "max_score": None,
            "min_score": None,
        }

    results = session.exec(
        select(HomeworkResult).where(HomeworkResult.student_id.in_(active_students))
    ).all()

    percentages = [r.percentage for r in results if r.percentage is not None]

    return {
        "class_id": class_id,
        "student_count": student_count,
        "total_homework": len(results),
        "avg_score": (sum(percentages) / len(percentages)) if percentages else None,
        "max_score": max(percentages) if percentages else None,
        "min_score": min(percentages) if percentages else None,
    }
