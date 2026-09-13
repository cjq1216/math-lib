"""
用户管理路由（仅管理员可访问）
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import hash_password
from app.models.user import User, UserRole

router = APIRouter()


@router.get("/")
def list_users(
    session: Annotated[Session, Depends(get_session)],
    skip: int = 0,
    limit: int = 50,
):
    """列出所有用户"""
    users = session.exec(select(User).offset(skip).limit(limit)).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "real_name": u.real_name,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.post("/")
def create_user(
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """创建用户"""
    # TODO: 加管理员权限校验
    if session.exec(select(User).where(User.username == payload["username"])).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=payload["username"],
        password_hash=hash_password(payload["password"]),
        real_name=payload["real_name"],
        email=payload.get("email"),
        role=UserRole(payload.get("role", "teacher")),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"id": user.id, "username": user.username}


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """更新用户（启用/禁用、改角色、改密码）"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    for k, v in payload.items():
        if k == "password":
            user.password_hash = hash_password(v)
        elif k == "role":
            user.role = UserRole(v)
        else:
            setattr(user, k, v)

    session.add(user)
    session.commit()
    return {"id": user.id}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """删除用户（软删：is_active=False）"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = False
    session.add(user)
    session.commit()
    return {"ok": True}
