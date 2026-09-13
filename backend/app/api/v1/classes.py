"""班级、任课教师和班级学生路由。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.dependencies import (
    can_access_student,
    get_current_user,
    require_admin,
    require_class_access,
)
from app.models.class_ import Class, ClassStudent, ClassTeacher
from app.models.student import Student
from app.models.user import User, UserRole
from app.schemas.class_ import (
    ClassCreate,
    ClassRead,
    ClassStudentRead,
    ClassTeacherRead,
    ClassTeacherSet,
    ClassUpdate,
)
from app.schemas.common import OkResponse
from app.services.audit_service import add_audit_event

router = APIRouter()


def _validate_teachers(session: Session, teacher_ids: set[int]) -> None:
    if not teacher_ids:
        return
    users = session.exec(select(User).where(User.id.in_(teacher_ids))).all()
    valid_ids = {
        user.id
        for user in users
        if user.is_active and user.role in {UserRole.ADMIN, UserRole.TEACHER}
    }
    missing = sorted(teacher_ids - valid_ids)
    if missing:
        raise HTTPException(status_code=422, detail=f"教师不存在或已禁用: {missing}")


def _sync_teachers(
    session: Session,
    class_id: int,
    teacher_ids: set[int],
    assigned_by: int,
) -> None:
    existing = session.exec(
        select(ClassTeacher).where(ClassTeacher.class_id == class_id)
    ).all()
    by_teacher = {item.teacher_id: item for item in existing}
    for teacher_id, relation in by_teacher.items():
        if teacher_id not in teacher_ids:
            session.delete(relation)
    for teacher_id in teacher_ids - set(by_teacher):
        session.add(
            ClassTeacher(
                class_id=class_id,
                teacher_id=teacher_id,
                assigned_by=assigned_by,
            )
        )


def _class_to_dict(class_: Class) -> dict:
    return {
        "id": class_.id,
        "name": class_.name,
        "grade": class_.grade,
        "semester": class_.semester,
        "head_teacher_id": class_.head_teacher_id,
        "notes": class_.notes,
        "is_active": class_.is_active,
    }


@router.post("/", response_model=ClassRead, status_code=status.HTTP_201_CREATED)
def create_class(
    payload: ClassCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """创建班级并建立可信教师关联。"""
    requested_teachers = set(payload.teacher_ids)
    if current_user.role == UserRole.TEACHER:
        if payload.head_teacher_id not in {None, current_user.id} or requested_teachers - {
            current_user.id
        }:
            raise HTTPException(status_code=403, detail="教师只能创建由自己负责的班级")
        head_teacher_id = current_user.id
        teacher_ids = {current_user.id}
    else:
        head_teacher_id = payload.head_teacher_id
        teacher_ids = requested_teachers | ({head_teacher_id} if head_teacher_id else set())
        _validate_teachers(session, teacher_ids)

    class_ = Class(
        name=payload.name,
        grade=payload.grade,
        semester=payload.semester,
        head_teacher_id=head_teacher_id,
        notes=payload.notes,
        created_by=current_user.id,
    )
    session.add(class_)
    session.flush()
    _sync_teachers(session, class_.id, teacher_ids, current_user.id)
    add_audit_event(
        session,
        action="create",
        resource_type="class",
        actor=current_user,
        resource_id=class_.id,
        changes={"teacher_ids": sorted(teacher_ids)},
        request=request,
    )
    session.commit()
    return _class_to_dict(class_)


@router.get("/", response_model=list[ClassRead])
def list_classes(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: bool = True,
) -> list[dict]:
    """管理员查看全部，教师仅查看任教班级。"""
    statement = select(Class).where(Class.is_active == is_active)
    if current_user.role == UserRole.TEACHER:
        statement = (
            statement.outerjoin(ClassTeacher, ClassTeacher.class_id == Class.id)
            .where(
                or_(
                    Class.head_teacher_id == current_user.id,
                    ClassTeacher.teacher_id == current_user.id,
                )
            )
            .distinct()
        )
    classes = session.exec(statement.offset(skip).limit(limit)).all()
    return [_class_to_dict(item) for item in classes]


@router.get("/{class_id}", response_model=ClassRead)
def get_class(class_: Annotated[Class, Depends(require_class_access)]) -> dict:
    """获取有权访问的班级。"""
    return _class_to_dict(class_)


@router.patch("/{class_id}", response_model=ClassRead)
def update_class(
    class_id: int,
    payload: ClassUpdate,
    request: Request,
    class_: Annotated[Class, Depends(require_class_access)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """更新班级；教师不能变更负责人或停用状态。"""
    updates = payload.model_dump(exclude_unset=True)
    protected_fields = {"head_teacher_id", "is_active"}
    if current_user.role != UserRole.ADMIN and protected_fields & updates.keys():
        raise HTTPException(status_code=403, detail="只有管理员可以变更班主任或班级状态")
    if "head_teacher_id" in updates and updates["head_teacher_id"] is not None:
        _validate_teachers(session, {updates["head_teacher_id"]})

    for field, value in updates.items():
        setattr(class_, field, value)
    class_.updated_at = datetime.utcnow()
    session.add(class_)
    if class_.head_teacher_id is not None:
        relations = {
            item.teacher_id
            for item in session.exec(
                select(ClassTeacher).where(ClassTeacher.class_id == class_id)
            ).all()
        }
        if class_.head_teacher_id not in relations:
            session.add(
                ClassTeacher(
                    class_id=class_id,
                    teacher_id=class_.head_teacher_id,
                    assigned_by=current_user.id,
                )
            )
    add_audit_event(
        session,
        action="update",
        resource_type="class",
        actor=current_user,
        resource_id=class_id,
        changes={"fields": sorted(updates)},
        request=request,
    )
    session.commit()
    return _class_to_dict(class_)


@router.get("/{class_id}/teachers", response_model=list[ClassTeacherRead])
def list_class_teachers(
    class_: Annotated[Class, Depends(require_class_access)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    """列出班级教师。"""
    users = session.exec(
        select(User)
        .join(ClassTeacher, ClassTeacher.teacher_id == User.id)
        .where(ClassTeacher.class_id == class_.id)
        .order_by(User.real_name)
    ).all()
    return [
        {"id": user.id, "username": user.username, "real_name": user.real_name}
        for user in users
    ]


@router.put("/{class_id}/teachers", response_model=list[ClassTeacherRead])
def set_class_teachers(
    class_id: int,
    payload: ClassTeacherSet,
    request: Request,
    class_: Annotated[Class, Depends(require_class_access)],
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> list[dict]:
    """由管理员全量设置班级任课教师。"""
    teacher_ids = set(payload.teacher_ids)
    if class_.head_teacher_id is not None:
        teacher_ids.add(class_.head_teacher_id)
    _validate_teachers(session, teacher_ids)
    _sync_teachers(session, class_id, teacher_ids, admin.id)
    add_audit_event(
        session,
        action="set_teachers",
        resource_type="class",
        actor=admin,
        resource_id=class_id,
        changes={"teacher_ids": sorted(teacher_ids)},
        request=request,
    )
    session.commit()
    return list_class_teachers(class_, session)


@router.get("/{class_id}/students", response_model=list[ClassStudentRead])
def list_class_students(
    class_: Annotated[Class, Depends(require_class_access)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    """列出当前仍在班的学生。"""
    rows = session.exec(
        select(Student, ClassStudent)
        .join(ClassStudent, ClassStudent.student_id == Student.id)
        .where(ClassStudent.class_id == class_.id)
        .where(ClassStudent.left_at.is_(None))
        .where(Student.is_active.is_(True))
        .order_by(Student.student_no)
    ).all()
    return [
        {
            "student_id": student.id,
            "student_no": student.student_no,
            "name": student.name,
            "gender": student.gender,
            "phone": student.phone,
        }
        for student, _relation in rows
    ]


@router.post("/{class_id}/students/{student_id}", response_model=OkResponse)
def add_student_to_class(
    student_id: int,
    request: Request,
    class_: Annotated[Class, Depends(require_class_access)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """加入学生；已离班关系会被重新激活。"""
    student = session.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    if (
        current_user.role != UserRole.ADMIN
        and student.created_by != current_user.id
        and not can_access_student(session, current_user, student_id)
    ):
        raise HTTPException(status_code=403, detail="无权将该学生加入班级")

    relation = session.exec(
        select(ClassStudent).where(
            ClassStudent.class_id == class_.id,
            ClassStudent.student_id == student_id,
        )
    ).first()
    if relation is None:
        relation = ClassStudent(class_id=class_.id, student_id=student_id)
    else:
        relation.left_at = None
        relation.joined_at = datetime.utcnow()
    session.add(relation)
    add_audit_event(
        session,
        action="add_student",
        resource_type="class",
        actor=current_user,
        resource_id=class_.id,
        changes={"student_id": student_id},
        request=request,
    )
    session.commit()
    return OkResponse()


@router.delete("/{class_id}/students/{student_id}", response_model=OkResponse)
def remove_student_from_class(
    student_id: int,
    request: Request,
    class_: Annotated[Class, Depends(require_class_access)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """将当前有效的学生关系标记为离班。"""
    relation = session.exec(
        select(ClassStudent).where(
            ClassStudent.class_id == class_.id,
            ClassStudent.student_id == student_id,
            ClassStudent.left_at.is_(None),
        )
    ).first()
    if relation is None:
        raise HTTPException(status_code=404, detail="有效班级关联不存在")
    relation.left_at = datetime.utcnow()
    session.add(relation)
    add_audit_event(
        session,
        action="remove_student",
        resource_type="class",
        actor=current_user,
        resource_id=class_.id,
        changes={"student_id": student_id},
        request=request,
    )
    session.commit()
    return OkResponse()
