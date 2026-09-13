"""
用户表 - 机构管理员 + 教师（学生不登录系统）
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class UserRole(str, Enum):
    """用户角色"""

    ADMIN = "admin"  # 机构管理员
    TEACHER = "teacher"  # 教师


class User(SQLModel, table=True):
    """用户表"""

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(max_length=64, unique=True, index=True, description="用户名")
    password_hash: str = Field(max_length=255, description="密码哈希")
    real_name: str = Field(max_length=64, description="真实姓名")
    email: Optional[str] = Field(default=None, max_length=128, description="邮箱")
    phone: Optional[str] = Field(default=None, max_length=20, description="电话")

    role: UserRole = Field(default=UserRole.TEACHER, description="角色")
    is_active: bool = Field(default=True, description="是否启用")
    avatar_url: Optional[str] = Field(default=None, max_length=512, description="头像")

    # 扩展字段
    subject: Optional[str] = Field(default=None, max_length=64, description="学科")
    notes: Optional[str] = Field(default=None, description="备注")

    # 审计
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = Field(default=None)
