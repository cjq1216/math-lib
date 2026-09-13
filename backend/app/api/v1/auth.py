"""
认证路由 - 登录/登出/获取当前用户
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import LoginResponse, RegisterRequest, TokenPayload

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
):
    """登录获取 token"""
    user = session.exec(select(User).where(User.username == form_data.username)).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    # 更新最后登录时间
    user.last_login_at = user.last_login_at or user.last_login_at
    session.add(user)
    session.commit()

    # 签发 token
    token = create_access_token(
        subject=user.id,
        extra={"role": user.role.value, "username": user.username},
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        real_name=user.real_name,
        role=user.role,
    )


@router.post("/register", response_model=LoginResponse)
def register(
    payload: RegisterRequest,
    session: Annotated[Session, Depends(get_session)],
):
    """
    注册（仅机构管理员可注册新用户）

    MVP 简化：第一个用户自动成为 admin
    """
    # 检查用户名是否已存在
    existing = session.exec(select(User).where(User.username == payload.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 是否为第一个用户 → 自动成为 admin
    is_first = session.exec(select(User)).first() is None

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name,
        email=payload.email,
        role=UserRole.ADMIN if is_first else UserRole.TEACHER,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_access_token(
        subject=user.id,
        extra={"role": user.role.value, "username": user.username},
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        real_name=user.real_name,
        role=user.role,
    )


@router.get("/me", response_model=TokenPayload)
def get_me():
    """获取当前登录用户信息"""
    # 实际实现需要 Depends 解析 token
    raise HTTPException(status_code=501, detail="待实现")
