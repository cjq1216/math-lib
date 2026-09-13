"""
认证相关 Pydantic schema
"""
from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class LoginResponse(BaseModel):
    """登录响应"""

    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    real_name: str
    role: UserRole


class RegisterRequest(BaseModel):
    """注册请求"""

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=72)
    real_name: str = Field(min_length=1, max_length=64)
    email: EmailStr | None = None


class TokenPayload(BaseModel):
    """Token payload"""

    sub: str
    role: str | None = None
    username: str | None = None
