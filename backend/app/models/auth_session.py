"""登录会话与 refresh token 轮换状态。"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class AuthSession(SQLModel, table=True):
    """一次用户登录会话。数据库仅保存 refresh token 的随机标识。"""

    __tablename__ = "auth_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    refresh_jti: str = Field(max_length=64, unique=True, index=True)
    expires_at: datetime = Field(index=True)
    revoked_at: Optional[datetime] = Field(default=None, index=True)
    last_used_at: Optional[datetime] = Field(default=None)
    ip_address: Optional[str] = Field(default=None, max_length=64)
    user_agent: Optional[str] = Field(default=None, max_length=512)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
