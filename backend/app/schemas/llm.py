"""LLM 与后台任务 API schema。"""

from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.background_task import TaskStatus, TaskType
from app.schemas.common import StrictSchema


class SplitRequest(StrictSchema):
    text: str = Field(min_length=1)
    source_id: int | None = None


class TagRequest(StrictSchema):
    stem: str = Field(min_length=1)
    options: list[str] | None = None
    answer: str | None = None
    question_id: int | None = None


class EmbedRequest(StrictSchema):
    text: str = Field(min_length=1)
    question_id: int | None = None


class TaskCreateResponse(StrictSchema):
    task_id: int
    status: TaskStatus
    message: str | None = None


class TaskRead(StrictSchema):
    task_id: int
    task_type: TaskType
    status: TaskStatus
    progress: int
    progress_message: str | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None


class TaskSummary(StrictSchema):
    task_id: int
    task_type: TaskType
    status: TaskStatus
    progress: int
    created_at: datetime
    finished_at: datetime | None = None
