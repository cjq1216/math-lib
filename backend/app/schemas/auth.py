"""认证相关请求与响应 schema。"""

from pydantic import EmailStr, Field, field_validator

from app.core.security import validate_password_length
from app.schemas.common import StrictSchema
from app.schemas.user import UserRead


class AuthResponse(StrictSchema):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class RegisterRequest(StrictSchema):
    username: str = Field(min_length=3, max_length=64)
    password: str
    real_name: str = Field(min_length=1, max_length=64)
    email: EmailStr | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_length(value)


class TokenPayload(StrictSchema):
    sub: str
    sid: int
    type: str
    jti: str | None = None
