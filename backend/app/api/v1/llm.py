"""LLM 切题、文档解析、打标、批量校对入库与向量检索路由。"""

from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from loguru import logger
from sqlmodel import Session, select

from app.core.database import SessionLocal, get_session
from app.core.dependencies import get_current_user
from app.models.background_task import BackgroundTask, TaskType
from app.models.knowledge_point import KnowledgePoint
from app.models.question import (
    Question,
    QuestionAnswer,
    QuestionKnowledge,
    QuestionType,
    SubQuestion,
)
from app.models.user import User, UserRole
from app.schemas.llm import (
    BatchCurateCommitRequest,
    BatchCurateCommitResponse,
    EmbedRequest,
    SimilarQuestionItem,
    SplitRequest,
    TagRequest,
    TaskCreateResponse,
    TaskRead,
    TaskSummary,
)
from app.services.audit_service import add_audit_event
from app.services.doc_extractor import DocumentExtractionError, extract_document_text
from app.services.llm_service import auto_tag_question, embed_text, split_exam_questions
from app.services.task_service import (
    fail_task,
    finish_task,
    schedule_task,
    start_task,
    update_progress,
)
from app.services.vector_service import find_similar_by_question_id, save_question_embedding

router = APIRouter()


def _ensure_question(session: Session, question_id: int | None) -> None:
    if question_id is not None and session.get(Question, question_id) is None:
        raise HTTPException(status_code=404, detail="题目不存在")


def _require_task_owner(task: BackgroundTask, current_user: User) -> None:
    if current_user.role != UserRole.ADMIN and task.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该任务")


def _match_knowledge_point(session: Session, name_or_code: str) -> KnowledgePoint | None:
    """多策略智能匹配知识点：精确名称 -> 编码 -> 大小写首尾空白容错 -> 包含子串匹配。"""
    clean = name_or_code.strip()
    if not clean:
        return None

    exact = session.exec(
        select(KnowledgePoint).where(
            KnowledgePoint.name == clean,
            KnowledgePoint.is_active.is_(True),
        )
    ).first()
    if exact:
        return exact

    by_code = session.exec(
        select(KnowledgePoint).where(
            KnowledgePoint.code == clean,
            KnowledgePoint.is_active.is_(True),
        )
    ).first()
    if by_code:
        return by_code

    lower_clean = clean.lower()
    all_kps = session.exec(
        select(KnowledgePoint).where(KnowledgePoint.is_active.is_(True))
    ).all()
    for kp in all_kps:
        if kp.name.strip().lower() == lower_clean:
            return kp

    cand_matches = [
        kp for kp in all_kps
        if (clean in kp.name or kp.name in clean) and len(kp.name) >= 2
    ]
    if cand_matches:
        cand_matches.sort(key=lambda k: abs(len(k.name) - len(clean)))
        return cand_matches[0]

    return None

@router.post("/split-doc", response_model=TaskCreateResponse)
async def split_exam_document(
    background_tasks: BackgroundTasks,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
    source_id: int | None = Query(default=None),
) -> TaskCreateResponse:
    """上传 Word (.docx) / PDF (.pdf) / 纯文本试卷文档，提取文本并异步切题。"""
    content = await file.read()
    filename = file.filename or "exam_doc"

    try:
        extracted = extract_document_text(filename, content)
    except DocumentExtractionError as e:
        raise HTTPException(status_code=422, detail=e.message) from None

    task = schedule_task(
        background_tasks=background_tasks,
        session=session,
        task_type=TaskType.SPLIT_EXAM,
        created_by=current_user.id,
        func=_do_split_with_progress,
        text=extracted.content,
        source_id=source_id,
        filename=filename,
        payload={"filename": filename, "chars": extracted.total_chars, "source_id": source_id},
    )

    add_audit_event(
        session,
        action="split_doc_task_created",
        resource_type="background_task",
        actor=current_user,
        resource_id=task.id,
        changes={"filename": filename, "chars": extracted.total_chars},
        request=request,
    )
    session.commit()

    return TaskCreateResponse(
        task_id=task.id,
        status=task.status,
        message=f"文档解析成功（共 {extracted.total_chars} 字符），切题任务已排队",
    )


@router.post("/split", response_model=TaskCreateResponse)
def split_exam(
    background_tasks: BackgroundTasks,
    payload: SplitRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TaskCreateResponse:
    """创建纯文本异步切题任务。"""
    task = schedule_task(
        background_tasks=background_tasks,
        session=session,
        created_by=current_user.id,
        func=_do_split_with_progress,
        text=payload.text,
        source_id=payload.source_id,
        payload={"chars": len(payload.text), "source_id": payload.source_id},
    )
    add_audit_event(
        session,
        action="split_task_created",
        resource_type="background_task",
        actor=current_user,
        resource_id=task.id,
        changes={"chars": len(payload.text)},
        request=request,
    )
    session.commit()
    return TaskCreateResponse(task_id=task.id, status=task.status)


@router.post("/tag", response_model=TaskCreateResponse)
def tag_question(
    background_tasks: BackgroundTasks,
    payload: TagRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TaskCreateResponse:
    """创建异步题目标注任务。"""
    _ensure_question(session, payload.question_id)
    task = schedule_task(
        background_tasks=background_tasks,
        session=session,
        created_by=current_user.id,
        func=_do_tag,
        stem=payload.stem,
        options=payload.options,
        answer=payload.answer,
        question_id=payload.question_id,
        payload={
            "stem": payload.stem[:200],
            "options": payload.options,
            "answer": payload.answer,
            "question_id": payload.question_id,
        },
    )
    add_audit_event(
        session,
        action="tag_task_created",
        resource_type="background_task",
        actor=current_user,
        resource_id=task.id,
        changes={"question_id": payload.question_id},
        request=request,
    )
    session.commit()
    return TaskCreateResponse(task_id=task.id, status=task.status)


@router.post("/embed", response_model=TaskCreateResponse)
def embed_question(
    background_tasks: BackgroundTasks,
    payload: EmbedRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TaskCreateResponse:
    _ensure_question(session, payload.question_id)
    task = schedule_task(
        background_tasks=background_tasks,
        session=session,
        task_type=TaskType.EMBED_QUESTION,
        created_by=current_user.id,
        func=_do_embed,
        text=payload.text,
        question_id=payload.question_id,
        payload={"chars": len(payload.text), "question_id": payload.question_id},
    )
    add_audit_event(
        session,
        action="embed_task_created",
        resource_type="background_task",
        actor=current_user,
        resource_id=task.id,
        changes={"question_id": payload.question_id},
        request=request,
    )
    session.commit()
    return TaskCreateResponse(task_id=task.id, status=task.status)


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task_status(
    task_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """轮询任务状态及结果，带所有者权限隔离。"""
    task = session.get(BackgroundTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _require_task_owner(task, current_user)

    duration = None
    if task.started_at and task.finished_at:
        duration = (task.finished_at - task.started_at).total_seconds()

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
        "duration_seconds": duration,
    }


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    """教师仅列出自己的任务，管理员列出全部任务。"""
    stmt = select(BackgroundTask)
    if current_user.role != UserRole.ADMIN:
        stmt = stmt.where(BackgroundTask.created_by == current_user.id)
    tasks = session.exec(stmt.order_by(BackgroundTask.created_at.desc()).limit(limit)).all()
    return [
        {
            "task_id": t.id,
            "task_type": t.task_type,
            "status": t.status,
            "progress": t.progress,
            "created_at": t.created_at,
            "finished_at": t.finished_at,
        }
        for t in tasks
    ]


@router.post("/commit-drafts", response_model=BatchCurateCommitResponse)
async def commit_split_drafts(
    payload: BatchCurateCommitRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BatchCurateCommitResponse:
    """人工校对后一键批量将切题草稿存入正式题库（R3聚合入库与向量持久化闭环）。"""
    from app.api.v1.questions import compute_question_checksum

    created_ids: list[int] = []

    for item in payload.questions:
        # 1. 题型与难度校验
        try:
            q_type = QuestionType(item.question_type)
        except ValueError:
            q_type = QuestionType.CHOICE_SINGLE if item.options else QuestionType.SOLUTION

        # 2. 计算 Checksum
        checksum = compute_question_checksum(item.stem, item.options)

        # 3. 创建题目主记录
        question = Question(
            stem=item.stem,
            options=item.options,
            question_type=q_type,
            difficulty=item.difficulty,
            total_score=item.total_score,
            answer=item.answer,
            analysis=item.analysis,
            source_id=payload.source_id,
            checksum=checksum,
            is_active=True,
            is_verified=True,  # 人工校对入库直接标记为已校对
            created_by=current_user.id,
        )
        session.add(question)
        session.flush()

        # 4. 插入小问
        if item.sub_questions:
            for s_idx, sub in enumerate(item.sub_questions):
                session.add(
                    SubQuestion(
                        question_id=question.id,
                        label=sub.get("label") or f"({s_idx + 1})",
                        stem=sub.get("stem"),
                        score=float(sub.get("score") or 0.0),
                        answer=sub.get("answer"),
                        analysis=sub.get("analysis"),
                        display_order=s_idx,
                    )
                )

        # 5. 插入主答案记录
        if item.answer:
            session.add(
                QuestionAnswer(
                    question_id=question.id,
                    blank_index=1,
                    answer_text=item.answer,
                    is_primary=True,
                )
            )

        # 6. 关联知识点（按名称匹配已有知识点）
        if item.knowledge_points:
            for kp_name in item.knowledge_points:
                clean_name = kp_name.strip()
                if not clean_name:
                    continue
                kp_obj = _match_knowledge_point(session, clean_name)
                if kp_obj:
                    # 避免重复
                    exists = session.exec(
                        select(QuestionKnowledge).where(
                            QuestionKnowledge.question_id == question.id,
                            QuestionKnowledge.knowledge_point_id == kp_obj.id,
                        )
                    ).first()
                    if not exists:
                        session.add(
                            QuestionKnowledge(
                                question_id=question.id,
                                knowledge_point_id=kp_obj.id,
                                is_primary=True,
                            )
                        )

        created_ids.append(question.id)

    add_audit_event(
        session,
        action="commit_split_drafts",
        resource_type="question",
        actor=current_user,
        changes={"count": len(created_ids), "question_ids": created_ids},
        request=request,
    )
    session.commit()

    # 7. 异步触发 Embedding 生成（自动平滑降级，不阻断）
    for q_id in created_ids:
        q_obj = session.get(Question, q_id)
        if q_obj:
            raw_text = f"{q_obj.stem} {q_obj.answer or ''} {q_obj.analysis or ''}"
            try:
                vec = await embed_text(raw_text)
                if vec:
                    save_question_embedding(session, q_obj.id, vec)
                    session.commit()
            except Exception as e:
                logger.warning(f"题目 #{q_id} 向量生成异常: {e}")

    return BatchCurateCommitResponse(
        created_count=len(created_ids),
        question_ids=created_ids,
    )


@router.get("/questions/{question_id}/similar", response_model=list[SimilarQuestionItem])
def get_similar_questions(
    question_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    top_k: int = Query(default=5, ge=1, le=20),
    threshold: float = Query(default=0.7, ge=0.0, le=1.0),
) -> list[dict]:
    """查询指定题目的相似题列表（基于内存余弦相似度算法）。"""
    question = session.get(Question, question_id)
    if not question or not question.is_active:
        raise HTTPException(status_code=404, detail="题目不存在或已停用")

    similar_list = find_similar_by_question_id(
        session=session,
        question_id=question_id,
        top_k=top_k,
        threshold=threshold,
    )
    return similar_list


# ===== 后台执行函数 =====


async def _do_split_with_progress(task_id: int, text: str, source_id: int | None = None, filename: str | None = None):
    """后台执行分段切题与实时进度更新。"""
    with SessionLocal() as session:
        start_task(session, task_id)

    def on_progress(percent: int, msg: str):
        with SessionLocal() as session:
            update_progress(session, task_id, percent, msg)

    try:
        res = await split_exam_questions(text, on_progress=on_progress)
        is_partial = res.get("partial", False)
        with SessionLocal() as session:
            finish_task(session, task_id, result=res, partial=is_partial)
    except Exception as e:
        logger.error(f"切题任务 #{task_id} 失败: {e}")
        with SessionLocal() as session:
            fail_task(session, task_id, e)


async def _do_tag(task_id: int, stem: str, options: list[str] | None, answer: str | None, question_id: int | None):
    """后台执行打标并自动写回题目。"""
    with SessionLocal() as session:
        start_task(session, task_id)
        update_progress(session, task_id, 30, "正在调用线上模型分析题干与考点...")

    try:
        res = await auto_tag_question(stem, options, answer, question_id)
        with SessionLocal() as session:
            update_progress(session, task_id, 80, "分析完成，正在更新题目元数据...")
            if question_id and "error" not in res:
                q = session.get(Question, question_id)
                if q:
                    if "difficulty" in res:
                        q.difficulty = res["difficulty"]
                    if "question_type" in res:
                        try:
                            q.question_type = QuestionType(res["question_type"])
                        except ValueError:
                            pass
                    session.add(q)
                    session.commit()
            finish_task(session, task_id, result=res)
    except Exception as e:
        logger.error(f"打标任务 #{task_id} 失败: {e}")
        with SessionLocal() as session:
            fail_task(session, task_id, e)


async def _do_embed(task_id: int, text: str, question_id: int | None):
    """后台执行 Embedding 生成与向量存储。"""
    with SessionLocal() as session:
        start_task(session, task_id)
        update_progress(session, task_id, 40, "正在调用线上 Embedding 接口计算文本向量...")

    try:
        vec = await embed_text(text)
        with SessionLocal() as session:
            if vec and question_id:
                save_question_embedding(session, question_id, vec)
                session.commit()
            finish_task(session, task_id, result={"stored": vec is not None, "dim": len(vec) if vec else 0})
    except Exception as e:
        logger.error(f"向量任务 #{task_id} 失败: {e}")
        with SessionLocal() as session:
            fail_task(session, task_id, e)
