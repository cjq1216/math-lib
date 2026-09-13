"""
题目 CRUD + 检索路由
"""

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, func, select

from app.core.database import get_session
from app.models.question import Question, QuestionType

router = APIRouter()


@router.post("/")
def create_question(
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """创建题目"""
    q = Question(
        stem=payload["stem"],
        stem_html=payload.get("stem_html"),
        question_type=QuestionType(payload.get("question_type", "choice_single")),
        difficulty=payload.get("difficulty", 3),
        total_score=payload.get("total_score", 10.0),
        options=payload.get("options"),
        answer=payload.get("answer"),
        analysis=payload.get("analysis"),
        tags=payload.get("tags"),
        created_by=payload.get("created_by"),
    )
    session.add(q)
    session.commit()
    session.refresh(q)
    return {"id": q.id}


@router.get("/")
def list_questions(
    session: Annotated[Session, Depends(get_session)],
    keyword: Optional[str] = None,
    question_type: Optional[str] = None,
    difficulty: Optional[int] = None,
    knowledge_point_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_active: bool = True,
):
    """题目列表 + 多条件筛选"""
    stmt = select(Question).where(Question.is_active == is_active)

    if keyword:
        stmt = stmt.where(Question.stem.contains(keyword))
    if question_type:
        stmt = stmt.where(Question.question_type == QuestionType(question_type))
    if difficulty:
        stmt = stmt.where(Question.difficulty == difficulty)
    if knowledge_point_id:
        from app.models.question import QuestionKnowledge

        stmt = stmt.where(
            Question.id.in_(
                select(QuestionKnowledge.question_id).where(
                    QuestionKnowledge.knowledge_point_id == knowledge_point_id
                )
            )
        )

    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()

    questions = session.exec(
        stmt.order_by(Question.created_at.desc()).offset(skip).limit(limit)
    ).all()

    return {
        "total": total,
        "items": [_q_to_dict(q) for q in questions],
    }


@router.get("/{question_id}")
def get_question(
    question_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """获取单个题目详情"""
    q = session.get(Question, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 关联小问
    from app.models.question import QuestionAnswer, QuestionKnowledge, SubQuestion

    sub_questions = session.exec(
        select(SubQuestion)
        .where(SubQuestion.question_id == question_id)
        .order_by(SubQuestion.display_order)
    ).all()
    answers = session.exec(
        select(QuestionAnswer).where(QuestionAnswer.question_id == question_id)
    ).all()
    kps = session.exec(
        select(QuestionKnowledge).where(QuestionKnowledge.question_id == question_id)
    ).all()

    return {
        **_q_to_dict(q),
        "sub_questions": [_sq_to_dict(sq) for sq in sub_questions],
        "answers": [_a_to_dict(a) for a in answers],
        "knowledge_points": [
            {"kp_id": kp.knowledge_point_id, "is_primary": kp.is_primary} for kp in kps
        ],
    }


@router.patch("/{question_id}")
def update_question(
    question_id: int,
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """更新题目"""
    q = session.get(Question, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    for k, v in payload.items():
        if k == "question_type":
            v = QuestionType(v)
        setattr(q, k, v)
    q.updated_at = datetime.utcnow()

    session.add(q)
    session.commit()
    return {"id": q.id}


@router.delete("/{question_id}")
def delete_question(
    question_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """软删题目"""
    q = session.get(Question, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    q.is_active = False
    session.add(q)
    session.commit()
    return {"ok": True}


@router.put("/{question_id}/knowledge")
def set_question_knowledge(
    question_id: int,
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """
    全量覆盖题目的知识点关联

    body: {"items": [{"kp_id": 1, "is_primary": true}, ...]}
    """
    from app.models.question import QuestionKnowledge

    q = session.get(Question, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 先删旧关联
    old = session.exec(
        select(QuestionKnowledge).where(QuestionKnowledge.question_id == question_id)
    ).all()
    for o in old:
        session.delete(o)
    session.flush()

    for item in payload.get("items", []):
        kp_id = item.get("kp_id")
        if not kp_id:
            continue
        session.add(
            QuestionKnowledge(
                question_id=question_id,
                knowledge_point_id=int(kp_id),
                is_primary=bool(item.get("is_primary", False)),
                weight=float(item.get("weight", 1.0)),
            )
        )
    session.commit()
    return {"ok": True, "count": len(payload.get("items", []))}


@router.put("/{question_id}/sub-questions")
def set_sub_questions(
    question_id: int,
    payload: dict,
    session: Annotated[Session, Depends(get_session)],
):
    """
    全量覆盖题目的小问

    body: {"items": [{"label": "(1)", "stem": "...", "score": 4, "answer": "..."}]}
    """
    from app.models.question import SubQuestion

    q = session.get(Question, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    old = session.exec(select(SubQuestion).where(SubQuestion.question_id == question_id)).all()
    for o in old:
        session.delete(o)
    session.flush()

    for idx, item in enumerate(payload.get("items", [])):
        session.add(
            SubQuestion(
                question_id=question_id,
                label=item.get("label") or f"({idx + 1})",
                stem=item.get("stem"),
                score=float(item.get("score", 0)),
                answer=item.get("answer"),
                display_order=idx,
            )
        )
    session.commit()
    return {"ok": True, "count": len(payload.get("items", []))}


# ====== 辅助函数 ======


def _q_to_dict(q: Question) -> dict:
    return {
        "id": q.id,
        "stem": q.stem,
        "question_type": q.question_type,
        "difficulty": q.difficulty,
        "total_score": q.total_score,
        "options": q.options,
        "answer": q.answer,
        "analysis": q.analysis,
        "tags": q.tags,
        "is_verified": q.is_verified,
        "created_at": q.created_at,
    }


def _sq_to_dict(sq) -> dict:
    return {
        "id": sq.id,
        "label": sq.label,
        "stem": sq.stem,
        "score": sq.score,
        "answer": sq.answer,
    }


def _a_to_dict(a) -> dict:
    return {
        "id": a.id,
        "blank_index": a.blank_index,
        "answer_text": a.answer_text,
        "is_primary": a.is_primary,
    }
