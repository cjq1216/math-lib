"""
试卷路由 - CRUD + 智能组卷
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.paper import Paper, PaperQuestion, PaperStatus

router = APIRouter()


@router.post("/")
def create_paper(
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """创建空白试卷"""
    p = Paper(
        title=payload["title"],
        description=payload.get("description"),
        total_score=payload.get("total_score", 100.0),
        duration_minutes=payload.get("duration_minutes", 90),
        grade=payload.get("grade"),
        semester=payload.get("semester"),
        tags=payload.get("tags"),
        status=PaperStatus.DRAFT,
        constraint_json=payload.get("constraint"),
        created_by=payload.get("created_by"),
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return {"id": p.id}


@router.get("/")
def list_papers(
    session: Annotated[Session, Depends(get_session)],
    skip: int = 0,
    limit: int = 20,
    status: str | None = None,
):
    """试卷列表"""
    stmt = select(Paper)
    if status:
        stmt = stmt.where(Paper.status == PaperStatus(status))
    stmt = stmt.order_by(Paper.created_at.desc()).offset(skip).limit(limit)
    papers = session.exec(stmt).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "total_score": p.total_score,
            "duration_minutes": p.duration_minutes,
            "status": p.status,
            "question_count": p.question_count,
            "created_at": p.created_at,
        }
        for p in papers
    ]


@router.get("/{paper_id}")
def get_paper(
    paper_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """试卷详情（含快照）"""
    p = session.get(Paper, paper_id)
    if not p:
        raise HTTPException(status_code=404, detail="试卷不存在")

    pq_list = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == paper_id)
        .order_by(PaperQuestion.display_order)
    ).all()

    return {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "total_score": p.total_score,
        "duration_minutes": p.duration_minutes,
        "status": p.status,
        "questions": [
            {
                "id": pq.id,
                "display_order": pq.display_order,
                "section": pq.section,
                "score": pq.score,
                "stem": pq.stem_snapshot,
                "answer": pq.answer_snapshot,
                "analysis": pq.analysis_snapshot,
                "options": pq.options_snapshot,
            }
            for pq in pq_list
        ],
    }


@router.post("/generate")
def generate_paper(
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """
    智能组卷入口

    调用智能组卷引擎，详见 app.services.paper_generator
    """
    from app.services.paper_generator import generate_paper as gen

    constraint = payload.get("constraint", {})
    title = payload.get("title", "智能组卷")

    paper, questions = gen(
        session=session,
        title=title,
        constraint=constraint,
        created_by=payload.get("created_by"),
    )

    return {
        "paper_id": paper.id,
        "question_count": len(questions),
        "total_score": paper.total_score,
        "questions": [
            {
                "id": pq.id,
                "display_order": pq.display_order,
                "section": pq.section,
                "score": pq.score,
                "stem": pq.stem_snapshot,
            }
            for pq in session.exec(
                select(PaperQuestion)
                .where(PaperQuestion.paper_id == paper.id)
                .order_by(PaperQuestion.display_order)
            ).all()
        ],
    }


@router.post("/{paper_id}/publish")
def publish_paper(
    paper_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """发布试卷"""
    p = session.get(Paper, paper_id)
    if not p:
        raise HTTPException(status_code=404, detail="试卷不存在")
    from datetime import datetime

    p.status = PaperStatus.PUBLISHED
    p.published_at = datetime.utcnow()
    session.add(p)
    session.commit()
    return {"ok": True}


@router.post("/{paper_id}/export")
def export_paper(
    paper_id: int,
    format: str = "word",  # word / markdown / pdf
    session: Annotated[Session, Depends(get_session)] = None,
):
    """导出试卷（占位）"""
    # TODO: 实现 Word / Markdown / PDF 导出
    return {
        "paper_id": paper_id,
        "format": format,
        "message": "导出功能开发中",
    }
