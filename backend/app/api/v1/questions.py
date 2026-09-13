"""题目 CRUD、检索与关联维护。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session, func, select

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.knowledge_point import KnowledgePoint
from app.models.question import Question, QuestionAnswer, QuestionKnowledge, SubQuestion
from app.models.user import User
from app.schemas.common import IdResponse, OkResponse
from app.schemas.question import (
    QuestionCreate,
    QuestionKnowledgeSet,
    QuestionListResponse,
    QuestionRead,
    QuestionUpdate,
    ReplaceResponse,
    SubQuestionSet,
)
from app.services.audit_service import add_audit_event

router = APIRouter()


@router.post("/", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def create_question(
    payload: QuestionCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdResponse:
    """创建题目，操作者由认证上下文注入。"""
    question = Question(**payload.model_dump(), created_by=current_user.id)
    session.add(question)
    session.flush()
    add_audit_event(
        session,
        action="create",
        resource_type="question",
        actor=current_user,
        resource_id=question.id,
        changes={"question_type": question.question_type.value, "difficulty": question.difficulty},
        request=request,
    )
    session.commit()
    return IdResponse(id=question.id)


@router.get("/", response_model=QuestionListResponse)
def list_questions(
    session: Annotated[Session, Depends(get_session)],
    keyword: str | None = None,
    question_type: str | None = None,
    difficulty: int | None = Query(default=None, ge=1, le=5),
    knowledge_point_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_active: bool = True,
) -> dict:
    """题目列表和多条件筛选。"""
    statement = select(Question).where(Question.is_active == is_active)
    if keyword:
        statement = statement.where(Question.stem.contains(keyword))
    if question_type:
        from app.models.question import QuestionType

        try:
            parsed_type = QuestionType(question_type)
        except ValueError:
            raise HTTPException(status_code=422, detail="无效的题型") from None
        statement = statement.where(Question.question_type == parsed_type)
    if difficulty:
        statement = statement.where(Question.difficulty == difficulty)
    if knowledge_point_id:
        statement = statement.where(
            Question.id.in_(
                select(QuestionKnowledge.question_id).where(
                    QuestionKnowledge.knowledge_point_id == knowledge_point_id
                )
            )
        )

    total = session.exec(select(func.count()).select_from(statement.subquery())).one()
    questions = session.exec(
        statement.order_by(Question.created_at.desc()).offset(skip).limit(limit)
    ).all()
    return {"total": total, "items": [_question_to_dict(item) for item in questions]}


@router.get("/{question_id}", response_model=QuestionRead)
def get_question(
    question_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    """获取题目详情。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")

    sub_questions = session.exec(
        select(SubQuestion)
        .where(SubQuestion.question_id == question_id)
        .order_by(SubQuestion.display_order)
    ).all()
    answers = session.exec(
        select(QuestionAnswer).where(QuestionAnswer.question_id == question_id)
    ).all()
    knowledge = session.exec(
        select(QuestionKnowledge).where(QuestionKnowledge.question_id == question_id)
    ).all()
    return {
        **_question_to_dict(question),
        "sub_questions": [_sub_question_to_dict(item) for item in sub_questions],
        "answers": [_answer_to_dict(item) for item in answers],
        "knowledge_points": [
            {"kp_id": item.knowledge_point_id, "is_primary": item.is_primary}
            for item in knowledge
        ],
    }


@router.patch("/{question_id}", response_model=IdResponse)
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdResponse:
    """按显式白名单更新题目。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(question, field, value)
    question.updated_at = datetime.utcnow()
    session.add(question)
    add_audit_event(
        session,
        action="update",
        resource_type="question",
        actor=current_user,
        resource_id=question.id,
        changes={"fields": sorted(updates)},
        request=request,
    )
    session.commit()
    return IdResponse(id=question.id)


@router.delete("/{question_id}", response_model=OkResponse)
def delete_question(
    question_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """软删题目。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    question.is_active = False
    question.updated_at = datetime.utcnow()
    session.add(question)
    add_audit_event(
        session,
        action="delete",
        resource_type="question",
        actor=current_user,
        resource_id=question.id,
        request=request,
    )
    session.commit()
    return OkResponse()


@router.put("/{question_id}/knowledge", response_model=ReplaceResponse)
def set_question_knowledge(
    question_id: int,
    payload: QuestionKnowledgeSet,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ReplaceResponse:
    """全量覆盖题目的知识点关联。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")

    kp_ids = [item.kp_id for item in payload.items]
    if len(kp_ids) != len(set(kp_ids)):
        raise HTTPException(status_code=422, detail="知识点不能重复")
    if sum(item.is_primary for item in payload.items) > 1:
        raise HTTPException(status_code=422, detail="最多只能设置一个主知识点")
    existing_ids = set(
        session.exec(select(KnowledgePoint.id).where(KnowledgePoint.id.in_(kp_ids))).all()
    ) if kp_ids else set()
    missing = sorted(set(kp_ids) - existing_ids)
    if missing:
        raise HTTPException(status_code=422, detail=f"知识点不存在: {missing}")

    for old in session.exec(
        select(QuestionKnowledge).where(QuestionKnowledge.question_id == question_id)
    ).all():
        session.delete(old)
    session.flush()
    for item in payload.items:
        session.add(
            QuestionKnowledge(
                question_id=question_id,
                knowledge_point_id=item.kp_id,
                is_primary=item.is_primary,
                weight=item.weight,
            )
        )
    add_audit_event(
        session,
        action="set_knowledge",
        resource_type="question",
        actor=current_user,
        resource_id=question_id,
        changes={"knowledge_point_ids": kp_ids},
        request=request,
    )
    session.commit()
    return ReplaceResponse(count=len(payload.items))


@router.put("/{question_id}/sub-questions", response_model=ReplaceResponse)
def set_sub_questions(
    question_id: int,
    payload: SubQuestionSet,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ReplaceResponse:
    """全量覆盖题目的小问。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")

    for old in session.exec(
        select(SubQuestion).where(SubQuestion.question_id == question_id)
    ).all():
        session.delete(old)
    session.flush()
    for index, item in enumerate(payload.items):
        session.add(
            SubQuestion(
                question_id=question_id,
                label=item.label or f"({index + 1})",
                stem=item.stem,
                score=item.score,
                answer=item.answer,
                analysis=item.analysis,
                display_order=index,
            )
        )
    add_audit_event(
        session,
        action="set_sub_questions",
        resource_type="question",
        actor=current_user,
        resource_id=question_id,
        changes={"count": len(payload.items)},
        request=request,
    )
    session.commit()
    return ReplaceResponse(count=len(payload.items))


def _question_to_dict(question: Question) -> dict:
    return {
        "id": question.id,
        "stem": question.stem,
        "question_type": question.question_type,
        "difficulty": question.difficulty,
        "total_score": question.total_score,
        "options": question.options,
        "answer": question.answer,
        "analysis": question.analysis,
        "tags": question.tags,
        "is_verified": question.is_verified,
        "created_at": question.created_at,
    }


def _sub_question_to_dict(sub_question: SubQuestion) -> dict:
    return {
        "id": sub_question.id,
        "label": sub_question.label,
        "stem": sub_question.stem,
        "score": sub_question.score,
        "answer": sub_question.answer,
    }


def _answer_to_dict(answer: QuestionAnswer) -> dict:
    return {
        "id": answer.id,
        "blank_index": answer.blank_index,
        "answer_text": answer.answer_text,
        "is_primary": answer.is_primary,
    }
