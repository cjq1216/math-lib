"""LLM、后台切题打标任务与向量检索 API schema。"""

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


class DocumentExtractResponse(StrictSchema):
    filename: str
    file_type: str
    total_chars: int
    page_count: int | None = None
    content: str


class SplitDraftQuestion(StrictSchema):
    number: str | None = None
    stem: str = Field(min_length=1)
    question_type: str = "choice_single"
    difficulty: int = Field(default=3, ge=1, le=5)
    total_score: float = Field(default=5.0, ge=0)
    options: list[str] | None = None
    sub_questions: list[dict[str, Any]] | None = None
    answer: str | None = None
    analysis: str | None = None
    knowledge_points: list[str] = Field(default_factory=list)


class BatchCurateCommitRequest(StrictSchema):
    questions: list[SplitDraftQuestion] = Field(min_length=1)
    source_id: int | None = None


class BatchCurateCommitResponse(StrictSchema):
    created_count: int
    question_ids: list[int]


class SimilarQuestionItem(StrictSchema):
    question_id: int
    similarity: float
    stem: str
    question_type: str
    difficulty: int
    total_score: float
