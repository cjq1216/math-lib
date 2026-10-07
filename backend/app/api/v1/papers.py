"""试卷 CRUD、智能组卷、题目微调与真实文件导出路由。"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.datetime_utils import utc_now
from app.core.dependencies import get_current_user
from app.models.paper import Paper, PaperQuestion, PaperStatus
from app.models.question import Question
from app.models.user import User
from app.schemas.common import IdResponse, OkResponse
from app.schemas.paper import (
    PaperCreate,
    PaperGenerateRequest,
    PaperGenerateResponse,
    PaperQuestionAddRequest,
    PaperQuestionRead,
    PaperQuestionReplaceRequest,
    PaperQuestionsReorderRequest,
    PaperQuestionUpdatePayload,
    PaperRead,
    PaperSummary,
)
from app.services.audit_service import add_audit_event
from app.services.paper_exporter import export_docx, export_markdown
from app.services.paper_generator import (
    SECTION_NAMES,
    ConstraintUnsatisfiableError,
)
from app.services.paper_generator import (
    generate_paper as run_generate_paper,
)

router = APIRouter()


def _paper_summary(paper: Paper) -> dict:
    return {
        "id": paper.id,
        "title": paper.title,
        "total_score": paper.total_score,
        "duration_minutes": paper.duration_minutes,
        "status": paper.status,
        "question_count": paper.question_count,
        "created_at": paper.created_at,
    }


def _pq_to_dict(pq: PaperQuestion) -> dict:
    return {
        "id": pq.id,
        "display_order": pq.display_order,
        "section": pq.section,
        "score": pq.score,
        "stem": pq.stem_snapshot,
        "answer": pq.answer_snapshot,
        "analysis": pq.analysis_snapshot,
        "options": pq.options_snapshot,
    }


@router.post("/", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def create_paper(
    payload: PaperCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdResponse:
    """创建空白试卷。"""
    values = payload.model_dump(exclude={"constraint"})
    paper = Paper(
        **values,
        status=PaperStatus.DRAFT,
        constraint_json=payload.constraint,
        created_by=current_user.id,
    )
    session.add(paper)
    session.flush()
    add_audit_event(
        session,
        action="create",
        resource_type="paper",
        actor=current_user,
        resource_id=paper.id,
        changes={"title": paper.title},
        request=request,
    )
    session.commit()
    return IdResponse(id=paper.id)


@router.get("/", response_model=list[PaperSummary])
def list_papers(
    session: Annotated[Session, Depends(get_session)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    paper_status: PaperStatus | None = Query(default=None, alias="status"),
) -> list[dict]:
    """列出机构共享试卷。"""
    statement = select(Paper)
    if paper_status:
        statement = statement.where(Paper.status == paper_status)
    papers = session.exec(
        statement.order_by(Paper.created_at.desc()).offset(skip).limit(limit)
    ).all()
    return [_paper_summary(paper) for paper in papers]


@router.get("/{paper_id}", response_model=PaperRead)
def get_paper(
    paper_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    """读取试卷详情及题目快照。"""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    questions = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == paper_id)
        .order_by(PaperQuestion.display_order, PaperQuestion.id)
    ).all()
    return {
        "id": paper.id,
        "title": paper.title,
        "description": paper.description,
        "total_score": paper.total_score,
        "duration_minutes": paper.duration_minutes,
        "status": paper.status,
        "questions": [_pq_to_dict(q) for q in questions],
    }


@router.post("/generate", response_model=PaperGenerateResponse)
def generate_paper(
    payload: PaperGenerateRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """调用分层贪心智能组卷引擎（支持四步拆分、硬约束达标与结构化报错）。"""
    constraint_dict = payload.constraint.model_dump()
    seed = constraint_dict.get("seed")
    type_scores = constraint_dict.get("type_scores")

    try:
        paper, paper_questions = run_generate_paper(
            session=session,
            title=payload.title,
            constraint=constraint_dict,
            created_by=current_user.id,
            seed=seed,
            score_strategy=type_scores,
        )
    except ConstraintUnsatisfiableError as e:
        raise HTTPException(
            status_code=422,
            detail=e.to_dict(),
        ) from None

    add_audit_event(
        session,
        action="generate",
        resource_type="paper",
        actor=current_user,
        resource_id=paper.id,
        changes={"question_count": len(paper_questions), "total_score": paper.total_score},
        request=request,
    )
    session.commit()

    return {
        "paper_id": paper.id,
        "question_count": len(paper_questions),
        "total_score": paper.total_score,
        "questions": [
            {
                "id": question.id,
                "display_order": question.display_order,
                "section": question.section,
                "score": question.score,
                "stem": question.stem_snapshot,
            }
            for question in paper_questions
        ],
    }


@router.post("/{paper_id}/publish", response_model=OkResponse)
def publish_paper(
    paper_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """发布试卷。"""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    paper.status = PaperStatus.PUBLISHED
    paper.published_at = utc_now()
    paper.updated_at = utc_now()
    session.add(paper)
    add_audit_event(
        session,
        action="publish",
        resource_type="paper",
        actor=current_user,
        resource_id=paper_id,
        request=request,
    )
    session.commit()
    return OkResponse()


@router.get("/{paper_id}/export")
@router.post("/{paper_id}/export")
def export_paper_file(
    paper_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    format: str = Query(default="word", pattern="^(word|markdown)$"),
) -> Response:
    """真实导出试卷快照为 Markdown 或 Word (.docx) 文件流并触发浏览器下载。"""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")

    questions = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == paper_id)
        .order_by(PaperQuestion.display_order, PaperQuestion.id)
    ).all()

    clean_title = re_clean_filename(paper.title)

    if format == "markdown":
        md_text = export_markdown(paper, questions)
        filename = f"{clean_title}.md"
        encoded_filename = quote(filename)
        add_audit_event(
            session,
            action="export",
            resource_type="paper",
            actor=current_user,
            resource_id=paper_id,
            changes={"format": "markdown", "filename": filename},
            request=request,
        )
        session.commit()
        return Response(
            content=md_text.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )

    # Word (.docx) 导出
    docx_bytes = export_docx(paper, questions)
    filename = f"{clean_title}.docx"
    encoded_filename = quote(filename)
    add_audit_event(
        session,
        action="export",
        resource_type="paper",
        actor=current_user,
        resource_id=paper_id,
        changes={"format": "word", "filename": filename},
        request=request,
    )
    session.commit()
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


# ===== 试卷题目微调接口（改分、替换、删除、排序、添加） =====


@router.put("/{paper_id}/questions/reorder", response_model=OkResponse)
def reorder_paper_questions(
    paper_id: int,
    payload: PaperQuestionsReorderRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """批量调整试卷题目的显示顺序。"""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")

    for item in payload.items:
        pq = session.get(PaperQuestion, item.paper_question_id)
        if pq and pq.paper_id == paper_id:
            pq.display_order = item.display_order
            session.add(pq)

    paper.updated_at = utc_now()
    session.add(paper)

    add_audit_event(
        session,
        action="reorder_paper_questions",
        resource_type="paper",
        actor=current_user,
        resource_id=paper_id,
        changes={"count": len(payload.items)},
        request=request,
    )
    session.commit()
    return OkResponse()


@router.put("/{paper_id}/questions/{paper_question_id}", response_model=PaperQuestionRead)
def update_paper_question(
    paper_id: int,
    paper_question_id: int,
    payload: PaperQuestionUpdatePayload,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """修改试卷中单道题目的分值、区段或题号，并自动重算试卷总分。"""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")

    pq = session.get(PaperQuestion, paper_question_id)
    if pq is None or pq.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="试卷题目不存在")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(pq, field, value)
    session.add(pq)
    session.flush()

    # 重新计算试卷总分
    all_pqs = session.exec(select(PaperQuestion).where(PaperQuestion.paper_id == paper_id)).all()
    paper.total_score = round(sum(q.score for q in all_pqs), 1)
    paper.updated_at = utc_now()
    session.add(paper)

    add_audit_event(
        session,
        action="update_paper_question",
        resource_type="paper",
        actor=current_user,
        resource_id=paper_id,
        changes={"paper_question_id": paper_question_id, "fields": updates},
        request=request,
    )
    session.commit()
    return _pq_to_dict(pq)


@router.delete("/{paper_id}/questions/{paper_question_id}", response_model=OkResponse)
def remove_paper_question(
    paper_id: int,
    paper_question_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """从试卷中删除单道题目，自动重排后续题号并重算试卷总分。"""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")

    pq = session.get(PaperQuestion, paper_question_id)
    if pq is None or pq.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="试卷题目不存在")

    session.delete(pq)
    session.flush()

    # 重排后续题号并更新总分
    remaining_pqs = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == paper_id)
        .order_by(PaperQuestion.display_order, PaperQuestion.id)
    ).all()

    for idx, item in enumerate(remaining_pqs, start=1):
        item.display_order = idx
        session.add(item)

    paper.question_count = len(remaining_pqs)
    paper.total_score = round(sum(q.score for q in remaining_pqs), 1)
    paper.updated_at = utc_now()
    session.add(paper)

    add_audit_event(
        session,
        action="remove_paper_question",
        resource_type="paper",
        actor=current_user,
        resource_id=paper_id,
        changes={"removed_pq_id": paper_question_id, "new_count": paper.question_count},
        request=request,
    )
    session.commit()
    return OkResponse()


@router.post("/{paper_id}/questions/{paper_question_id}/replace", response_model=PaperQuestionRead)
def replace_paper_question(
    paper_id: int,
    paper_question_id: int,
    payload: PaperQuestionReplaceRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """在试卷中替换题目（可指定目标题号或在题库同类型同难度中智能寻找替补题），写入新快照。"""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")

    pq = session.get(PaperQuestion, paper_question_id)
    if pq is None or pq.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="试卷题目不存在")

    # 当前试卷中已存在的 question_id 集合（排除自身）
    existing_q_ids = set(
        session.exec(
            select(PaperQuestion.question_id).where(
                PaperQuestion.paper_id == paper_id,
                PaperQuestion.id != paper_question_id,
            )
        ).all()
    )

    if payload.target_question_id:
        target_q = session.get(Question, payload.target_question_id)
        if target_q is None or not target_q.is_active:
            raise HTTPException(status_code=422, detail="目标替换题目不存在或已停用")
        if target_q.id in existing_q_ids:
            raise HTTPException(status_code=422, detail="目标替换题目已在当前试卷中")
    else:
        # 智能替补：同题型、相近难度、不在卷内
        original_q = session.get(Question, pq.question_id)
        target_type = original_q.question_type if original_q else None
        target_diff = original_q.difficulty if original_q else 3

        candidates_stmt = select(Question).where(
            Question.is_active == True,
            ~Question.id.in_(existing_q_ids | {pq.question_id}),
        )
        if target_type:
            candidates_stmt = candidates_stmt.where(Question.question_type == target_type)

        candidates = session.exec(candidates_stmt).all()
        if not candidates:
            raise HTTPException(status_code=422, detail="题库中无可用同类型替补题目")

        # 优先挑难度一致或差值最小的
        candidates.sort(key=lambda q: abs(q.difficulty - target_diff))
        target_q = candidates[0]

    # 更新题目快照
    pq.question_id = target_q.id
    pq.stem_snapshot = target_q.stem
    pq.answer_snapshot = target_q.answer
    pq.analysis_snapshot = target_q.analysis
    pq.options_snapshot = target_q.options
    session.add(pq)

    paper.updated_at = utc_now()
    session.add(paper)

    add_audit_event(
        session,
        action="replace_paper_question",
        resource_type="paper",
        actor=current_user,
        resource_id=paper_id,
        changes={
            "paper_question_id": paper_question_id,
            "old_question_id": pq.question_id,
            "new_question_id": target_q.id,
        },
        request=request,
    )
    session.commit()
    return _pq_to_dict(pq)


@router.post("/{paper_id}/questions", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def add_paper_question(
    paper_id: int,
    payload: PaperQuestionAddRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdResponse:
    """手动添加单道题目到试卷（写入快照）。"""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")

    q = session.get(Question, payload.question_id)
    if q is None or not q.is_active:
        raise HTTPException(status_code=422, detail="题目不存在或已停用")

    exists = session.exec(
        select(PaperQuestion).where(
            PaperQuestion.paper_id == paper_id,
            PaperQuestion.question_id == payload.question_id,
        )
    ).first()
    if exists:
        raise HTTPException(status_code=422, detail="该题已在当前试卷中")

    max_order = session.exec(
        select(PaperQuestion.display_order)
        .where(PaperQuestion.paper_id == paper_id)
        .order_by(PaperQuestion.display_order.desc())
    ).first() or 0

    section_name = payload.section or SECTION_NAMES.get(q.question_type.value, "其他题型")
    pq = PaperQuestion(
        paper_id=paper_id,
        question_id=q.id,
        section=section_name,
        display_order=max_order + 1,
        score=payload.score,
        stem_snapshot=q.stem,
        answer_snapshot=q.answer,
        analysis_snapshot=q.analysis,
        options_snapshot=q.options,
    )
    session.add(pq)
    session.flush()

    # 更新试卷统计
    all_pqs = session.exec(select(PaperQuestion).where(PaperQuestion.paper_id == paper_id)).all()
    paper.question_count = len(all_pqs)
    paper.total_score = round(sum(item.score for item in all_pqs), 1)
    paper.updated_at = utc_now()
    session.add(paper)

    add_audit_event(
        session,
        action="add_paper_question",
        resource_type="paper",
        actor=current_user,
        resource_id=paper_id,
        changes={"question_id": q.id, "display_order": pq.display_order, "score": pq.score},
        request=request,
    )
    session.commit()
    return IdResponse(id=pq.id)



def re_clean_filename(text: str) -> str:
    """清理文件名中的非法字符。"""
    cleaned = "".join(c for c in text if c.isalnum() or c in ("-", "_", " ", "(", ")", "（", "）")).strip()
    return cleaned or "试卷导出"
