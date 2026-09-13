"""管理员用户管理路由。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session, func, select

from app.core.database import get_session
from app.core.dependencies import require_admin
from app.core.security import hash_password
from app.models.auth_session import AuthSession
from app.models.user import User, UserRole
from app.schemas.common import OkResponse
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.audit_service import add_audit_event

router = APIRouter()


def _active_admin_count(session: Session) -> int:
    return session.exec(
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
    ).one()


def _ensure_admin_survives(session: Session, target: User, next_role: UserRole, active: bool) -> None:
    if (
        target.role == UserRole.ADMIN
        and target.is_active
        and (next_role != UserRole.ADMIN or not active)
        and _active_admin_count(session) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能禁用或降级最后一个有效管理员",
        )


def _revoke_user_sessions(session: Session, user_id: int) -> None:
    now = datetime.utcnow()
    sessions = session.exec(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    ).all()
    for auth_session in sessions:
        auth_session.revoked_at = now
        session.add(auth_session)


@router.get("/", response_model=list[UserRead])
def list_users(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[User, Depends(require_admin)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> list[User]:
    """列出用户。"""
    return list(session.exec(select(User).offset(skip).limit(limit)).all())


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> User:
    """由管理员创建教师或其他管理员。"""
    if session.exec(select(User.id).where(User.username == payload.username)).first() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name,
        email=payload.email,
        phone=payload.phone,
        role=payload.role,
        subject=payload.subject,
        notes=payload.notes,
    )
    session.add(user)
    session.flush()
    add_audit_event(
        session,
        action="create",
        resource_type="user",
        actor=admin,
        resource_id=user.id,
        changes={"username": user.username, "role": user.role.value},
        request=request,
    )
    session.commit()
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> User:
    """按白名单更新用户。"""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    updates = payload.model_dump(exclude_unset=True)
    next_role = updates.get("role", user.role)
    next_active = updates.get("is_active", user.is_active)
    if not next_active and user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前管理员")
    _ensure_admin_survives(session, user, next_role, next_active)

    before = {
        "real_name": user.real_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role.value,
        "is_active": user.is_active,
        "subject": user.subject,
    }
    password_changed = "password" in updates
    for field, value in updates.items():
        if field == "password":
            user.password_hash = hash_password(value)
        else:
            setattr(user, field, value)
    user.updated_at = datetime.utcnow()
    session.add(user)

    if password_changed or not user.is_active:
        _revoke_user_sessions(session, user.id)

    after = {
        "real_name": user.real_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role.value,
        "is_active": user.is_active,
        "subject": user.subject,
        "password_changed": password_changed,
    }
    add_audit_event(
        session,
        action="update",
        resource_type="user",
        actor=admin,
        resource_id=user.id,
        changes={"before": before, "after": after},
        request=request,
    )
    session.commit()
    return user


def _disable_user(session: Session, admin: User, user_id: int, request: Request) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前管理员")
    _ensure_admin_survives(session, user, user.role, False)

    user.is_active = False
    user.updated_at = datetime.utcnow()
    session.add(user)
    _revoke_user_sessions(session, user.id)
    add_audit_event(
        session,
        action="disable",
        resource_type="user",
        actor=admin,
        resource_id=user.id,
        changes={"is_active": False},
        request=request,
    )
    session.commit()


@router.post("/{user_id}/disable", response_model=OkResponse)
def disable_user(
    user_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> OkResponse:
    """软禁用用户并撤销其全部会话。"""
    _disable_user(session, admin, user_id, request)
    return OkResponse()


@router.delete("/{user_id}", response_model=OkResponse, deprecated=True)
def delete_user(
    user_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[User, Depends(require_admin)],
) -> OkResponse:
    """兼容旧客户端的禁用入口。"""
    _disable_user(session, admin, user_id, request)
    return OkResponse()
