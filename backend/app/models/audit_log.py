"""
操作日志表 - 审计追踪
"""
from datetime import datetime
from typing import Optional

from sqlmodel import JSON, Field, SQLModel


class AuditLog(SQLModel, table=True):
    """操作日志"""

    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)

    # 操作人
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    username: Optional[str] = Field(default=None, max_length=64)

    # 操作
    action: str = Field(max_length=32, index=True, description="create/update/delete/login/...")
    resource_type: str = Field(max_length=32, index=True, description="question/paper/homework/...")
    resource_id: Optional[int] = Field(default=None, index=True)

    # 变更前/后（JSON）
    changes: Optional[dict] = Field(default=None, sa_type=JSON)

    # 请求信息
    ip_address: Optional[str] = Field(default=None, max_length=64)
    user_agent: Optional[str] = Field(default=None, max_length=512)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
