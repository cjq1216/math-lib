"""认证路由：初始化、登录、刷新、注销和当前用户。"""

from datetime import datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies import AuthContext, get_auth_context, get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.auth_session import AuthSession
from app.models.user import User, UserRole
from app.schemas.auth import AuthResponse, RegisterRequest
from app.schemas.common import OkResponse
from app.schemas.user import UserRead
from app.services.audit_service import add_audit_event

router = APIRouter()


def _unauthorized(detail: str = "登录状态无效或已过期") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=token,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure or settings.app_env == "production",
        samesite=settings.auth_cookie_samesite,
        path=f"{settings.api_v1_prefix}/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        secure=settings.auth_cookie_secure or settings.app_env == "production",
        samesite=settings.auth_cookie_samesite,
        path=f"{settings.api_v1_prefix}/auth",
    )


def _issue_session(
    session: Session,
    user: User,
    request: Request,
) -> tuple[str, str]:
    refresh_jti = uuid4().hex
    auth_session = AuthSession(
        user_id=user.id,
        refresh_jti=refresh_jti,
        expires_at=datetime.utcnow()
        + timedelta(days=settings.jwt_refresh_token_expire_days),
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
    )
    session.add(auth_session)
    session.flush()

    access_token = create_access_token(
        subject=user.id,
        session_id=auth_session.id,
        extra={"role": user.role.value, "username": user.username},
    )
    refresh_token, _, expires_at = create_refresh_token(
        subject=user.id,
        session_id=auth_session.id,
        jti=refresh_jti,
    )
    auth_session.expires_at = expires_at
    session.add(auth_session)
    return access_token, refresh_token


@router.post("/login", response_model=AuthResponse)
def login(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
) -> AuthResponse:
    """登录并创建可轮换的 refresh 会话。"""
    user = session.exec(select(User).where(User.username == form_data.username)).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        add_audit_event(
            session,
            action="login_failed",
            resource_type="auth",
            actor_username=form_data.username,
            changes={"reason": "invalid_credentials"},
            request=request,
        )
        session.commit()
        raise _unauthorized("用户名或密码错误")

    if not user.is_active:
        add_audit_event(
            session,
            action="login_failed",
            resource_type="auth",
            actor=user,
            changes={"reason": "disabled"},
            request=request,
        )
        session.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被禁用")

    user.last_login_at = datetime.utcnow()
    session.add(user)
    access_token, refresh_token = _issue_session(session, user, request)
    add_audit_event(
        session,
        action="login_success",
        resource_type="auth",
        actor=user,
        request=request,
    )
    session.commit()
    _set_refresh_cookie(response, refresh_token)
    return AuthResponse(access_token=access_token, user=user)


@router.post("/register", response_model=AuthResponse)
def register(
    payload: RegisterRequest,
    response: Response,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AuthResponse:
    """仅在空库中初始化第一个管理员。"""
    if session.exec(select(User.id).limit(1)).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="系统初始化已完成，请由管理员创建用户",
        )

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name,
        email=payload.email,
        role=UserRole.ADMIN,
    )
    session.add(user)
    session.flush()
    access_token, refresh_token = _issue_session(session, user, request)
    add_audit_event(
        session,
        action="bootstrap_admin",
        resource_type="user",
        actor=user,
        resource_id=user.id,
        request=request,
    )
    session.commit()
    _set_refresh_cookie(response, refresh_token)
    return AuthResponse(access_token=access_token, user=user)


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    response: Response,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AuthResponse:
    """轮换 HttpOnly refresh cookie 并签发新的 access token。"""
    token = request.cookies.get(settings.auth_refresh_cookie_name)
    payload = decode_token(token, expected_type="refresh") if token else None
    if payload is None:
        _clear_refresh_cookie(response)
        raise _unauthorized("刷新凭证无效或已过期")

    try:
        user_id = int(payload["sub"])
        session_id = int(payload["sid"])
        refresh_jti = str(payload["jti"])
    except (KeyError, TypeError, ValueError):
        _clear_refresh_cookie(response)
        raise _unauthorized("刷新凭证无效") from None

    auth_session = session.get(AuthSession, session_id)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= datetime.utcnow()
    ):
        _clear_refresh_cookie(response)
        raise _unauthorized("刷新会话已失效")

    if auth_session.refresh_jti != refresh_jti:
        auth_session.revoked_at = datetime.utcnow()
        session.add(auth_session)
        session.commit()
        _clear_refresh_cookie(response)
        raise _unauthorized("刷新凭证已被轮换")

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        auth_session.revoked_at = datetime.utcnow()
        session.add(auth_session)
        session.commit()
        _clear_refresh_cookie(response)
        raise _unauthorized("用户不存在或已被禁用")

    new_jti = uuid4().hex
    new_refresh_token, _, expires_at = create_refresh_token(
        subject=user.id,
        session_id=auth_session.id,
        jti=new_jti,
    )
    auth_session.refresh_jti = new_jti
    auth_session.expires_at = expires_at
    auth_session.last_used_at = datetime.utcnow()
    session.add(auth_session)
    access_token = create_access_token(
        subject=user.id,
        session_id=auth_session.id,
        extra={"role": user.role.value, "username": user.username},
    )
    session.commit()
    _set_refresh_cookie(response, new_refresh_token)
    return AuthResponse(access_token=access_token, user=user)


@router.post("/logout", response_model=OkResponse)
def logout(
    response: Response,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_session)],
) -> OkResponse:
    """撤销当前会话并清理 refresh cookie。"""
    context.auth_session.revoked_at = datetime.utcnow()
    session.add(context.auth_session)
    add_audit_event(
        session,
        action="logout",
        resource_type="auth",
        actor=context.user,
        request=request,
    )
    session.commit()
    _clear_refresh_cookie(response)
    return OkResponse()


@router.get("/me", response_model=UserRead)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """返回数据库中的当前用户。"""
    return current_user
