"""
班级路由
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.class_ import Class, ClassStudent
from app.models.student import Student

router = APIRouter()


@router.post("/")
def create_class(
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """创建班级"""
    c = Class(
        name=payload["name"],
        grade=payload["grade"],
        semester=payload["semester"],
        head_teacher_id=payload.get("head_teacher_id"),
        notes=payload.get("notes"),
        created_by=payload.get("created_by"),
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return {"id": c.id}


@router.get("/")
def list_classes(
    session: Annotated[Session, Depends(get_session)],
    skip: int = 0,
    limit: int = 50,
    is_active: bool = True,
):
    """班级列表"""
    stmt = select(Class).where(Class.is_active == is_active).offset(skip).limit(limit)
    classes = session.exec(stmt).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "grade": c.grade,
            "semester": c.semester,
            "head_teacher_id": c.head_teacher_id,
        }
        for c in classes
    ]


@router.get("/{class_id}/students")
def list_class_students(
    class_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """班级学生列表"""
    stmt = (
        select(Student, ClassStudent)
        .join(ClassStudent, ClassStudent.student_id == Student.id)
        .where(ClassStudent.class_id == class_id)
        .where(Student.is_active == True)
        .order_by(Student.student_no)
    )
    rows = session.exec(stmt).all()
    return [
        {
            "student_id": s.id,
            "student_no": s.student_no,
            "name": s.name,
            "gender": s.gender,
            "phone": s.phone,
        }
        for s, _ in rows
    ]


@router.post("/{class_id}/students/{student_id}")
def add_student_to_class(
    class_id: int,
    student_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """添加学生到班级"""
    # 检查是否已存在
    existing = session.exec(
        select(ClassStudent)
        .where(ClassStudent.class_id == class_id)
        .where(ClassStudent.student_id == student_id)
    ).first()
    if existing:
        return {"ok": True, "already_exists": True}

    cs = ClassStudent(class_id=class_id, student_id=student_id)
    session.add(cs)
    session.commit()
    return {"ok": True}


@router.delete("/{class_id}/students/{student_id}")
def remove_student_from_class(
    class_id: int,
    student_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """从班级移除学生"""
    from datetime import datetime

    cs = session.exec(
        select(ClassStudent)
        .where(ClassStudent.class_id == class_id)
        .where(ClassStudent.student_id == student_id)
    ).first()
    if not cs:
        raise HTTPException(status_code=404, detail="关联不存在")
    cs.left_at = datetime.utcnow()
    session.add(cs)
    session.commit()
    return {"ok": True}
