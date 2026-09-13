"""
LLM 路由 - 切题/打标/Embedding

支持两种调用方式：
1. 同步（immediate）：小任务，立即返回
2. 异步（background）：大任务（>10秒），返回 task_id 轮询
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.background_task import BackgroundTask, TaskType
from app.services.llm_service import auto_tag_question, embed_text, split_exam_questions
from app.services.task_service import schedule_task

router = APIRouter()


@router.post("/split")
def split_exam(
    payload: dict,
    bg: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
):
    """
    切题（异步）

    输入试卷文本 → 返回 task_id → 前端轮询查进度
    """
    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    task = schedule_task(
        background_tasks=bg,
        session=session,
        task_type=TaskType.SPLIT_EXAM,
        func=_do_split,
        payload={"text_length": len(text)},
        resource_type="source",
        resource_id=payload.get("source_id"),
        created_by=payload.get("created_by"),
        text=text,
    )

    return {
        "task_id": task.id,
        "status": task.status,
        "message": "切题任务已创建，请轮询 /api/v1/llm/tasks/{id} 查进度",
    }


@router.post("/tag")
def tag_question(
    payload: dict,
    bg: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
):
    """打标（异步）"""
    task = schedule_task(
        background_tasks=bg,
        session=session,
        task_type=TaskType.AUTO_TAG,
        func=_do_tag,
        payload={
            "stem_length": len(payload.get("stem", "")),
            "has_options": bool(payload.get("options")),
        },
        resource_type="question",
        resource_id=payload.get("question_id"),
        created_by=payload.get("created_by"),
        stem=payload.get("stem"),
        options=payload.get("options"),
        answer=payload.get("answer"),
        question_id=payload.get("question_id"),
    )
    return {"task_id": task.id, "status": task.status}


@router.post("/embed")
def embed(
    payload: dict,
    bg: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
):
    """Embedding（异步）"""
    task = schedule_task(
        background_tasks=bg,
        session=session,
        task_type=TaskType.EMBED_QUESTION,
        func=_do_embed,
        payload={"text_length": len(payload.get("text", ""))},
        resource_type="question",
        resource_id=payload.get("question_id"),
        created_by=payload.get("created_by"),
        text=payload.get("text"),
        question_id=payload.get("question_id"),
    )
    return {"task_id": task.id, "status": task.status}


@router.get("/tasks/{task_id}")
def get_task_status(
    task_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """轮询任务状态"""
    task = session.get(BackgroundTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

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


@router.get("/tasks")
def list_tasks(
    session: Annotated[Session, Depends(get_session)],
    status: str | None = None,
    task_type: str | None = None,
    skip: int = 0,
    limit: int = 20,
):
    """任务列表"""
    stmt = select(BackgroundTask).order_by(BackgroundTask.created_at.desc())
    if status:
        stmt = stmt.where(BackgroundTask.status == status)
    if task_type:
        stmt = stmt.where(BackgroundTask.task_type == task_type)
    stmt = stmt.offset(skip).limit(limit)

    return [
        {
            "task_id": t.id,
            "task_type": t.task_type,
            "status": t.status,
            "progress": t.progress,
            "created_at": t.created_at,
            "finished_at": t.finished_at,
        }
        for t in session.exec(stmt).all()
    ]


# ====== 后台任务具体实现 ======


async def _do_split(text: str, source_id: int | None = None):
    """后台执行切题"""
    # 执行切题
    result = await split_exam_questions(text)
    return result


async def _do_tag(
    stem: str,
    options: list[str] | None = None,
    answer: str | None = None,
    question_id: int | None = None,
):
    """后台执行打标"""
    result = await auto_tag_question(stem=stem, options=options, answer=answer)

    # 把打标结果写回 question 表
    if question_id and "error" not in result:
        from app.core.database import SessionLocal
        from app.models.question import Question, QuestionType

        with SessionLocal() as session:
            q = session.get(Question, question_id)
            if q:
                if "question_type" in result:
                    try:
                        q.question_type = QuestionType(result["question_type"])
                    except ValueError:
                        pass
                if "difficulty" in result:
                    q.difficulty = int(result["difficulty"])
                q.is_verified = False
                q.updated_at = datetime.utcnow()
                session.add(q)
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
