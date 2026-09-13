"""
学情分析路由 - 薄弱点/班级排行/针对性出题
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.services.analytics_service import (
    generate_targeted_practice,
    get_class_overview,
    get_class_ranking,
    get_student_overview,
    get_student_weak_points,
    recompute_student_stats,
)

router = APIRouter()


@router.post("/students/{student_id}/recompute")
def recompute_student(
    student_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """重算某学生学情（手动触发）"""
    recompute_student_stats(session, student_id)
    return {"ok": True}


@router.get("/students/{student_id}/overview")
def student_overview(
    student_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """学生学情概览"""
    return get_student_overview(session, student_id)


@router.get("/students/{student_id}/weak-points")
def student_weak_points(
    student_id: int,
    session: Annotated[Session, Depends(get_session)],
    top_n: int = 5,
):
    """学生薄弱知识点"""
    return get_student_weak_points(session, student_id, top_n)


@router.post("/students/{student_id}/targeted-practice")
def targeted_practice(
    student_id: int,
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """针对性练习（基于薄弱点选题）"""
    count = payload.get("count", 5)
    difficulty_min = payload.get("difficulty_min", 1)
    difficulty_max = payload.get("difficulty_max", 5)
    return generate_targeted_practice(session, student_id, count, difficulty_min, difficulty_max)


@router.get("/classes/{class_id}/ranking")
def class_ranking(
    class_id: int,
    session: Annotated[Session, Depends(get_session)],
    homework_id: int | None = None,
):
    """班级排行（按作业）"""
    return get_class_ranking(session, class_id, homework_id)


@router.get("/classes/{class_id}/overview")
def class_overview(
    class_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """班级整体学情"""
    return get_class_overview(session, class_id)
