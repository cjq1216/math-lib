"""学生和班级学情分析路由。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.dependencies import get_current_user, require_class_access, require_student_access
from app.models.class_ import Class
from app.models.homework import Homework, HomeworkStatus, HomeworkStudent, HomeworkType
from app.models.paper import Paper, PaperQuestion, PaperStatus
from app.models.question import Question
from app.models.student import Student
from app.models.user import User
from app.schemas.analytics import (
    ClassOverview,
    CreateTargetedHomeworkRequest,
    CreateTargetedHomeworkResponse,
    RankRow,
    StudentOverview,
    TargetedPracticeRequest,
    TargetedPracticeResponse,
    WeakPointRead,
)
from app.schemas.common import OkResponse
from app.services.analytics_service import (
    generate_targeted_practice,
    get_class_overview,
    get_class_ranking,
    get_student_overview,
    get_student_weak_points,
    recompute_student_stats,
)
from app.services.audit_service import add_audit_event

router = APIRouter()


@router.post("/students/{student_id}/recompute", response_model=OkResponse)
def recompute_student(
    request: Request,
    student: Annotated[Student, Depends(require_student_access)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """重算有权访问学生的学情。"""
    recompute_student_stats(session, student.id)
    add_audit_event(
        session,
        action="recompute",
        resource_type="student_analytics",
        actor=current_user,
        resource_id=student.id,
        request=request,
    )
    session.commit()
    return OkResponse()


@router.get("/students/{student_id}/overview", response_model=StudentOverview)
def student_overview(
    student: Annotated[Student, Depends(require_student_access)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    """学生学情概览。"""
    return get_student_overview(session, student.id)


@router.get("/students/{student_id}/weak-points", response_model=list[WeakPointRead])
def student_weak_points(
    student: Annotated[Student, Depends(require_student_access)],
    session: Annotated[Session, Depends(get_session)],
    top_n: int = Query(5, ge=1, le=100),
) -> list[dict]:
    """学生薄弱知识点。"""
    return get_student_weak_points(session, student.id, top_n)


@router.post(
    "/students/{student_id}/targeted-practice",
    response_model=TargetedPracticeResponse,
)
def targeted_practice(
    payload: TargetedPracticeRequest,
    student: Annotated[Student, Depends(require_student_access)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    """按薄弱点为有权访问的学生选题。"""
    return generate_targeted_practice(
        session,
        student.id,
        payload.count,
        payload.difficulty_min,
        payload.difficulty_max,
    )


@router.post(
    "/students/{student_id}/create-targeted-homework",
    response_model=CreateTargetedHomeworkResponse,
)
def create_targeted_homework(
    payload: CreateTargetedHomeworkRequest,
    request: Request,
    student: Annotated[Student, Depends(require_student_access)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """根据针对性练习题目一键生成专属试卷并直接下发作业。"""
    q_ids = list(dict.fromkeys(payload.question_ids))
    questions = session.exec(select(Question).where(Question.id.in_(q_ids))).all()
    q_map = {q.id: q for q in questions}

    missing = [qid for qid in q_ids if qid not in q_map]
    if missing:
        raise HTTPException(status_code=404, detail=f"题目 ID {missing} 不存在")

    total_score = len(q_ids) * payload.score_per_question

    # 1. 创建试卷并写入题目快照
    paper = Paper(
        title=payload.title,
        description=f"为学生 {student.name} 生成的薄弱知识点针对性巩固练习卷",
        total_score=total_score,
        duration_minutes=max(30, len(q_ids) * 3),
        status=PaperStatus.PUBLISHED,
        created_by=current_user.id,
    )
    session.add(paper)
    session.flush()

    for idx, qid in enumerate(q_ids, start=1):
        q = q_map[qid]
        session.add(
            PaperQuestion(
                paper_id=paper.id,
                question_id=q.id,
                display_order=idx,
                section="针对性练习",
                score=payload.score_per_question,
                stem_snapshot=q.stem,
                answer_snapshot=q.answer,
                analysis_snapshot=q.analysis,
                options_snapshot=q.options,
            )
        )
    session.flush()

    # 2. 下发作业并记录名单快照
    homework = Homework(
        title=payload.title,
        type=HomeworkType.HOMEWORK,
        status=HomeworkStatus.ASSIGNED,
        paper_id=paper.id,
        class_ids=[],
        student_ids=[student.id],
        assigned_at=datetime.utcnow(),
        created_by=current_user.id,
    )
    session.add(homework)
    session.flush()

    session.add(
        HomeworkStudent(
            homework_id=homework.id,
            student_id=student.id,
            class_id=None,
        )
    )
    session.flush()

    add_audit_event(
        session,
        action="create_targeted_homework",
        resource_type="homework",
        actor=current_user,
        resource_id=homework.id,
        changes={
            "paper_id": paper.id,
            "student_id": student.id,
            "question_count": len(q_ids),
        },
        request=request,
    )
    session.commit()

    return {
        "homework_id": homework.id,
        "paper_id": paper.id,
        "title": homework.title,
    }


@router.get("/classes/{class_id}/ranking", response_model=list[RankRow])
def class_ranking(
    class_: Annotated[Class, Depends(require_class_access)],
    session: Annotated[Session, Depends(get_session)],
    homework_id: int | None = None,
) -> list[dict]:
    """有权访问班级的成绩排行。"""
    return get_class_ranking(session, class_.id, homework_id)


@router.get("/classes/{class_id}/overview", response_model=ClassOverview)
def class_overview(
    class_: Annotated[Class, Depends(require_class_access)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    """有权访问班级的整体学情。"""
    return get_class_overview(session, class_.id)
