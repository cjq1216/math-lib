"""
后台任务状态追踪

异步任务（切题/打标/Embedding）需要一个 status 表，
前端轮询查进度。
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlmodel import JSON, Field, SQLModel


class TaskStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"      # 排队中
    RUNNING = "running"      # 执行中
    SUCCESS = "success"      # 成功
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 取消


class TaskType(str, Enum):
    """任务类型"""

    SPLIT_EXAM = "split_exam"   # 切题
    AUTO_TAG = "auto_tag"       # 打标
    EMBED_QUESTION = "embed_question"  # Embedding
    GENERATE_TARGETED = "generate_targeted"  # 针对性出题
    IMPORT_PAPER = "import_paper"  # 试卷导入


class BackgroundTask(SQLModel, table=True):
    """后台任务记录"""

    __tablename__ = "background_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)

    # 任务类型
    task_type: TaskType = Field(index=True)
    status: TaskStatus = Field(default=TaskStatus.PENDING, index=True)

    # 输入参数（JSON）
    payload: Optional[dict[str, Any]] = Field(default=None, sa_type=JSON)

    # 输出结果（JSON）
    result: Optional[dict[str, Any]] = Field(default=None, sa_type=JSON)

    # 进度信息
    progress: int = Field(default=0, description="0-100")
    progress_message: Optional[str] = Field(default=None, max_length=512)

    # 错误信息
    error_message: Optional[str] = Field(default=None, max_length=2000)
    error_traceback: Optional[str] = Field(default=None)

    # 关联资源（如切题任务关联到 source_id）
    resource_type: Optional[str] = Field(default=None, max_length=32)
    resource_id: Optional[int] = Field(default=None, index=True)

    # 触发者
    created_by: Optional[int] = Field(default=None, foreign_key="users.id")

    # 时间
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)

    # 任务估算时长（秒）
    estimated_duration_seconds: Optional[int] = Field(default=None)
