"""用户管理请求与响应 schema。"""

from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.core.security import validate_password_length
from app.models.user import UserRole
from app.schemas.common import OrmSchema, StrictSchema


class UserRead(OrmSchema):

    id: int
    username: str
    real_name: str
    email: EmailStr | None = None
    phone: str | None = None
    role: UserRole
    is_active: bool
    avatar_url: str | None = None
    subject: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class UserCreate(StrictSchema):
    username: str = Field(min_length=3, max_length=64)
    password: str
    real_name: str = Field(min_length=1, max_length=64)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    role: UserRole = UserRole.TEACHER
    subject: str | None = Field(default=None, max_length=64)
    notes: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_length(value)


class UserUpdate(StrictSchema):
    real_name: str | None = Field(default=None, min_length=1, max_length=64)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    role: UserRole | None = None
    is_active: bool | None = None
    avatar_url: str | None = Field(default=None, max_length=512)
    subject: str | None = Field(default=None, max_length=64)
    notes: str | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None) -> str | None:
        return validate_password_length(value) if value is not None else None
