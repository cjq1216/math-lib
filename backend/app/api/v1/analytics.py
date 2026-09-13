"""学生和班级学情分析路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user, require_class_access, require_student_access
from app.models.class_ import Class
from app.models.student import Student
from app.models.user import User
from app.schemas.analytics import (
    ClassOverview,
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
