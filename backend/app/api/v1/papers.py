"""试卷 CRUD、智能组卷和发布路由。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.paper import Paper, PaperQuestion, PaperStatus
from app.models.user import User
from app.schemas.common import IdResponse, OkResponse
from app.schemas.paper import (
    PaperCreate,
    PaperGenerateRequest,
    PaperGenerateResponse,
    PaperRead,
    PaperSummary,
)
from app.services.audit_service import add_audit_event

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
        .order_by(PaperQuestion.display_order)
    ).all()
    return {
        "id": paper.id,
        "title": paper.title,
        "description": paper.description,
        "total_score": paper.total_score,
        "duration_minutes": paper.duration_minutes,
        "status": paper.status,
        "questions": [
            {
                "id": question.id,
                "display_order": question.display_order,
                "section": question.section,
                "score": question.score,
                "stem": question.stem_snapshot,
                "answer": question.answer_snapshot,
                "analysis": question.analysis_snapshot,
                "options": question.options_snapshot,
            }
            for question in questions
        ],
    }


@router.post("/generate", response_model=PaperGenerateResponse)
def generate_paper(
    payload: PaperGenerateRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """调用分层贪心组卷引擎。"""
    from app.services.paper_generator import generate_paper as generate

    paper, paper_questions = generate(
        session=session,
        title=payload.title,
        constraint=payload.constraint.model_dump(),
        created_by=current_user.id,
    )
    add_audit_event(
        session,
        action="generate",
        resource_type="paper",
        actor=current_user,
        resource_id=paper.id,
        changes={"question_count": len(paper_questions)},
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
    paper.published_at = datetime.utcnow()
    paper.updated_at = datetime.utcnow()
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


@router.post("/{paper_id}/export", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def export_paper(
    paper_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    format: str = Query(default="word", pattern="^(word|markdown|pdf)$"),
) -> None:
    """R4 前明确返回未实现，不再伪装成成功导出。"""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    add_audit_event(
        session,
        action="export_requested",
        resource_type="paper",
        actor=current_user,
        resource_id=paper_id,
        changes={"format": format, "implemented": False},
        request=request,
    )
    session.commit()
    raise HTTPException(status_code=501, detail="试卷导出将在 R4 实现")
