"""统一认证、角色和对象访问依赖。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import or_
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import get_session
from app.core.security import decode_token
from app.models.auth_session import AuthSession
from app.models.class_ import Class, ClassStudent, ClassTeacher
from app.models.homework import Homework
from app.models.student import Student
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


@dataclass(frozen=True)
class AuthContext:
    """已验证的 access token、登录会话和数据库用户。"""

    user: User
    auth_session: AuthSession
    claims: dict[str, Any]


def _unauthorized(detail: str = "登录状态无效或已过期") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_auth_context(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> AuthContext:
    """解析 access token，并实时校验会话和用户状态。"""
    payload = decode_token(token, expected_type="access")
    if payload is None:
        raise _unauthorized()

    try:
        user_id = int(payload["sub"])
        session_id = int(payload["sid"])
    except (KeyError, TypeError, ValueError):
        raise _unauthorized() from None

    auth_session = session.get(AuthSession, session_id)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= datetime.utcnow()
    ):
        raise _unauthorized()

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("用户不存在或已被禁用")

    return AuthContext(user=user, auth_session=auth_session, claims=payload)


def get_current_user(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> User:
    """返回数据库中的当前用户。"""
    return context.user


def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """仅允许管理员。"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


def require_teacher_or_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """允许当前系统的管理员或教师角色。"""
    if current_user.role not in {UserRole.ADMIN, UserRole.TEACHER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return current_user


def can_access_class(session: Session, current_user: User, class_id: int) -> bool:
    """判断当前用户能否访问指定班级。"""
    if current_user.role == UserRole.ADMIN:
        return session.get(Class, class_id) is not None

    statement = (
        select(Class.id)
        .outerjoin(ClassTeacher, ClassTeacher.class_id == Class.id)
        .where(Class.id == class_id)
        .where(
            or_(
                Class.head_teacher_id == current_user.id,
                ClassTeacher.teacher_id == current_user.id,
            )
        )
    )
    return session.exec(statement).first() is not None


def require_class_access(
    class_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Class:
    """加载班级并执行管理员/任课教师访问检查。"""
    class_ = session.get(Class, class_id)
    if class_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="班级不存在")
    if not can_access_class(session, current_user, class_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该班级")
    return class_


def can_access_student(session: Session, current_user: User, student_id: int) -> bool:
    """判断当前用户能否访问指定学生。"""
    if current_user.role == UserRole.ADMIN:
        return session.get(Student, student_id) is not None

    statement = (
        select(ClassStudent.id)
        .join(Class, Class.id == ClassStudent.class_id)
        .outerjoin(ClassTeacher, ClassTeacher.class_id == Class.id)
        .where(ClassStudent.student_id == student_id)
        .where(ClassStudent.left_at.is_(None))
        .where(
            or_(
                Class.head_teacher_id == current_user.id,
                ClassTeacher.teacher_id == current_user.id,
            )
        )
    )
    return session.exec(statement).first() is not None


def require_student_access(
    student_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Student:
    """加载学生并执行管理员/任课教师访问检查。"""
    student = session.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学生不存在")
    if not can_access_student(session, current_user, student_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该学生")
    return student


def can_access_homework(session: Session, current_user: User, homework: Homework) -> bool:
    """判断当前用户能否访问仍使用 JSON 关联的作业。"""
    if current_user.role == UserRole.ADMIN or homework.created_by == current_user.id:
        return True

    class_ids = homework.class_ids or []
    student_ids = homework.student_ids or []
    if not class_ids and not student_ids:
        return False
    return all(
        can_access_class(session, current_user, class_id) for class_id in class_ids
    ) and all(
        can_access_student(session, current_user, student_id) for student_id in student_ids
    )


def require_homework_access(
    homework_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Homework:
    """加载作业并校验访问范围。"""
    homework = session.get(Homework, homework_id)
    if homework is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作业不存在")
    if not can_access_homework(session, current_user, homework):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该作业")
    return homework
