"""LLM 切题、打标、Embedding 与任务状态路由。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.background_task import BackgroundTask, TaskStatus, TaskType
from app.models.question import Question
from app.models.user import User, UserRole
from app.schemas.llm import (
    EmbedRequest,
    SplitRequest,
    TagRequest,
    TaskCreateResponse,
    TaskRead,
    TaskSummary,
)
from app.services.llm_service import auto_tag_question, embed_text, split_exam_questions
from app.services.task_service import schedule_task

router = APIRouter()


def _ensure_question(session: Session, question_id: int | None) -> None:
    if question_id is not None and session.get(Question, question_id) is None:
        raise HTTPException(status_code=404, detail="题目不存在")


def _require_task_owner(task: BackgroundTask, current_user: User) -> None:
    if current_user.role != UserRole.ADMIN and task.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该任务")


@router.post("/split", response_model=TaskCreateResponse)
def split_exam(
    payload: SplitRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TaskCreateResponse:
    """创建异步切题任务。"""
    task = schedule_task(
        background_tasks=background_tasks,
        session=session,
        task_type=TaskType.SPLIT_EXAM,
        func=_do_split,
        payload={"text_length": len(payload.text)},
        resource_type="source",
        resource_id=payload.source_id,
        created_by=current_user.id,
        text=payload.text,
        source_id=payload.source_id,
    )
    return TaskCreateResponse(
        task_id=task.id,
        status=task.status,
        message="切题任务已创建，请轮询任务状态",
    )


@router.post("/tag", response_model=TaskCreateResponse)
def tag_question(
    payload: TagRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TaskCreateResponse:
    """创建异步题目标注任务。"""
    _ensure_question(session, payload.question_id)
    task = schedule_task(
        background_tasks=background_tasks,
        session=session,
        task_type=TaskType.AUTO_TAG,
        func=_do_tag,
        payload={
            "stem_length": len(payload.stem),
            "has_options": bool(payload.options),
        },
        resource_type="question",
        resource_id=payload.question_id,
        created_by=current_user.id,
        stem=payload.stem,
        options=payload.options,
        answer=payload.answer,
        question_id=payload.question_id,
    )
    return TaskCreateResponse(task_id=task.id, status=task.status)


@router.post("/embed", response_model=TaskCreateResponse)
def embed_question(
    payload: EmbedRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TaskCreateResponse:
    """创建异步 Embedding 任务。"""
    _ensure_question(session, payload.question_id)
    task = schedule_task(
        background_tasks=background_tasks,
        session=session,
        task_type=TaskType.EMBED_QUESTION,
        func=_do_embed,
        payload={"text_length": len(payload.text)},
        resource_type="question",
        resource_id=payload.question_id,
        created_by=current_user.id,
        text=payload.text,
        question_id=payload.question_id,
    )
    return TaskCreateResponse(task_id=task.id, status=task.status)


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task_status(
    task_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """轮询自己创建的任务；管理员可查看全部。"""
    task = session.get(BackgroundTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    _require_task_owner(task, current_user)
    return {
        "task_id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "progress": task.progress,
        "progress_message": task.progress_message,
        "result": task.result,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "duration_seconds": (
            (task.finished_at - task.started_at).total_seconds()
            if task.started_at and task.finished_at
            else None
        ),
    }


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    task_type: TaskType | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    """教师仅列出自己的任务，管理员列出全部。"""
    statement = select(BackgroundTask).order_by(BackgroundTask.created_at.desc())
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(BackgroundTask.created_by == current_user.id)
    if task_status:
        statement = statement.where(BackgroundTask.status == task_status)
    if task_type:
        statement = statement.where(BackgroundTask.task_type == task_type)
    tasks = session.exec(statement.offset(skip).limit(limit)).all()
    return [
        {
            "task_id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "progress": task.progress,
            "created_at": task.created_at,
            "finished_at": task.finished_at,
        }
        for task in tasks
    ]


async def _do_split(text: str, source_id: int | None = None):
    """后台执行切题。"""
    return await split_exam_questions(text)


async def _do_tag(
    stem: str,
    options: list[str] | None = None,
    answer: str | None = None,
    question_id: int | None = None,
):
    """后台执行打标并写回题目。"""
    result = await auto_tag_question(stem=stem, options=options, answer=answer)
    if question_id and "error" not in result:
        from app.core.database import SessionLocal
        from app.models.question import QuestionType

        with SessionLocal() as session:
            question = session.get(Question, question_id)
            if question:
                if "question_type" in result:
                    try:
                        question.question_type = QuestionType(result["question_type"])
                    except ValueError:
                        pass
                if "difficulty" in result:
                    question.difficulty = int(result["difficulty"])
                question.is_verified = False
                question.updated_at = datetime.utcnow()
                session.add(question)
                session.commit()
    return result


async def _do_embed(text: str, question_id: int | None = None):
    """生成并持久化 Embedding，不要求安装 sqlite-vec。"""
    vector = await embed_text(text)
    from app.core.config import settings

    if len(vector) != settings.embedding_dim:
        raise ValueError(f"Embedding 维度不匹配：期望 {settings.embedding_dim}，实际 {len(vector)}")
    if question_id:
        from app.core.database import SessionLocal
        from app.models.question_embedding import QuestionEmbedding

        with SessionLocal() as session:
            record = session.get(QuestionEmbedding, question_id)
            if record:
                record.embedding = vector
                record.dimensions = len(vector)
                record.model = settings.embedding_model
                record.updated_at = datetime.utcnow()
            else:
                record = QuestionEmbedding(
                    question_id=question_id,
                    embedding=vector,
                    dimensions=len(vector),
                    model=settings.embedding_model,
                )
            session.add(record)
            session.commit()
    return {"dim": len(vector), "stored": question_id is not None}
