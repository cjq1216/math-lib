"""题目 CRUD、检索、聚合写入与关联维护。"""

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session, func, select

from app.core.database import get_session
from app.core.datetime_utils import utc_now
from app.core.dependencies import get_current_user
from app.models.knowledge_point import KnowledgePoint
from app.models.media import MediaResource, QuestionMedia
from app.models.question import (
    Question,
    QuestionAnswer,
    QuestionKnowledge,
    QuestionType,
    SubQuestion,
)
from app.models.user import User
from app.schemas.common import IdResponse, OkResponse
from app.schemas.media import QuestionMediaAssociatePayload
from app.schemas.question import (
    QuestionCreate,
    QuestionKnowledgeInput,
    QuestionKnowledgeSet,
    QuestionListResponse,
    QuestionMediaInput,
    QuestionRead,
    QuestionUpdate,
    ReplaceResponse,
    SubQuestionSet,
)
from app.services.audit_service import add_audit_event

router = APIRouter()


def compute_question_checksum(stem: str, options: list[str] | None = None) -> str:
    """计算题目题干与选项的标准去重 Checksum。"""
    raw_stem = stem.strip()
    opts = [o.strip() for o in (options or []) if o.strip()]
    content = f"{raw_stem}|{json.dumps(opts, ensure_ascii=False)}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _validate_knowledge_points(
    session: Session, kp_inputs: list[QuestionKnowledgeInput]
) -> None:
    kp_ids = [item.kp_id for item in kp_inputs]
    if len(kp_ids) != len(set(kp_ids)):
        raise HTTPException(status_code=422, detail="知识点不能重复")
    if sum(item.is_primary for item in kp_inputs) > 1:
        raise HTTPException(status_code=422, detail="最多只能设置一个主知识点")
    if kp_ids:
        existing_ids = set(
            session.exec(
                select(KnowledgePoint.id).where(
                    KnowledgePoint.id.in_(kp_ids),
                    KnowledgePoint.is_active.is_(True),
                )
            ).all()
        )
        missing = sorted(set(kp_ids) - existing_ids)
        if missing:
            raise HTTPException(status_code=422, detail=f"知识点不存在或已停用: {missing}")


def _validate_media_items(
    session: Session, media_inputs: list[QuestionMediaInput]
) -> None:
    if not media_inputs:
        return
    pairs = [(item.media_id, item.usage_type) for item in media_inputs]
    if len(pairs) != len(set(pairs)):
        raise HTTPException(status_code=422, detail="同一媒体在同一种用途下不能重复关联")

    media_ids = [item.media_id for item in media_inputs]
    existing_ids = set(
        session.exec(
            select(MediaResource.id).where(MediaResource.id.in_(media_ids))
        ).all()
    )
    missing = sorted(set(media_ids) - existing_ids)
    if missing:
        raise HTTPException(status_code=422, detail=f"媒体资源不存在: {missing}")


@router.post("/", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def create_question(
    payload: QuestionCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdResponse:
    """单事务聚合创建题目（包含主表、小问、多空答案、知识点和媒体关联）。"""
    raw_data = payload.model_dump()
    sub_questions_data = raw_data.pop("sub_questions", None) or []
    answers_data = raw_data.pop("answers", None) or []
    kps_data = raw_data.pop("knowledge_points", None) or []
    media_data = raw_data.pop("media_items", None) or []

    # 1. 预校验知识点与媒体合法性
    if payload.knowledge_points:
        _validate_knowledge_points(session, payload.knowledge_points)
    if payload.media_items:
        _validate_media_items(session, payload.media_items)

    # 2. 计算 Checksum
    checksum = compute_question_checksum(payload.stem, payload.options)

    # 3. 创建题目主表记录
    question = Question(
        **raw_data,
        checksum=checksum,
        created_by=current_user.id,
    )
    session.add(question)
    session.flush()

    # 4. 插入小问
    for index, sub in enumerate(sub_questions_data):
        session.add(
            SubQuestion(
                question_id=question.id,
                label=sub.get("label") or f"({index + 1})",
                stem=sub.get("stem"),
                score=sub.get("score", 0.0),
                answer=sub.get("answer"),
                analysis=sub.get("analysis"),
                display_order=sub.get("display_order", index),
            )
        )

    # 5. 插入多空答案与匹配规则
    for ans in answers_data:
        session.add(
            QuestionAnswer(
                question_id=question.id,
                blank_index=ans.get("blank_index", 1),
                answer_text=ans["answer_text"],
                is_primary=ans.get("is_primary", True),
                match_rule=ans.get("match_rule"),
            )
        )

    # 6. 插入知识点关联
    for kp in kps_data:
        session.add(
            QuestionKnowledge(
                question_id=question.id,
                knowledge_point_id=kp["kp_id"],
                is_primary=kp.get("is_primary", False),
                weight=kp.get("weight", 1.0),
            )
        )

    # 7. 插入媒体关联并增加引用计数
    for index, med in enumerate(media_data):
        session.add(
            QuestionMedia(
                question_id=question.id,
                media_id=med["media_id"],
                usage_type=med["usage_type"],
                display_order=med.get("display_order", index),
                alt_text=med.get("alt_text"),
                caption=med.get("caption"),
            )
        )
        media_res = session.get(MediaResource, med["media_id"])
        if media_res:
            media_res.reference_count += 1
            session.add(media_res)

    # 8. 记录审计并统一提交
    add_audit_event(
        session,
        action="create",
        resource_type="question",
        actor=current_user,
        resource_id=question.id,
        changes={
            "question_type": question.question_type.value,
            "difficulty": question.difficulty,
            "sub_questions_count": len(sub_questions_data),
            "answers_count": len(answers_data),
            "kps_count": len(kps_data),
            "media_count": len(media_data),
        },
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
    is_verified: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_active: bool = True,
) -> dict:
    """题目列表和多条件筛选。"""
    statement = select(Question).where(Question.is_active == is_active)
    if keyword:
        statement = statement.where(Question.stem.contains(keyword))
    if question_type:
        try:
            parsed_type = QuestionType(question_type)
        except ValueError:
            raise HTTPException(status_code=422, detail="无效的题型") from None
        statement = statement.where(Question.question_type == parsed_type)
    if difficulty:
        statement = statement.where(Question.difficulty == difficulty)
    if is_verified is not None:
        statement = statement.where(Question.is_verified == is_verified)
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
    """获取题目详情，包含小问、答案与匹配规则、知识点和媒体列表。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")

    sub_questions = session.exec(
        select(SubQuestion)
        .where(SubQuestion.question_id == question_id)
        .order_by(SubQuestion.display_order, SubQuestion.id)
    ).all()
    answers = session.exec(
        select(QuestionAnswer)
        .where(QuestionAnswer.question_id == question_id)
        .order_by(QuestionAnswer.blank_index, QuestionAnswer.id)
    ).all()
    knowledge = session.exec(
        select(QuestionKnowledge)
        .where(QuestionKnowledge.question_id == question_id)
        .order_by(QuestionKnowledge.is_primary.desc(), QuestionKnowledge.weight.desc())
    ).all()

    # 查询关联媒体信息
    qm_rows = session.exec(
        select(QuestionMedia, MediaResource)
        .join(MediaResource, QuestionMedia.media_id == MediaResource.id)
        .where(QuestionMedia.question_id == question_id)
        .order_by(QuestionMedia.display_order, QuestionMedia.id)
    ).all()

    media_items = []
    for qm, mr in qm_rows:
        media_items.append(
            {
                "id": qm.id,
                "media_id": qm.media_id,
                "usage_type": qm.usage_type,
                "display_order": qm.display_order,
                "alt_text": qm.alt_text,
                "caption": qm.caption,
                "access_url": mr.access_url,
                "original_name": mr.original_name,
            }
        )

    return {
        **_question_to_dict(question),
        "sub_questions": [_sub_question_to_dict(item) for item in sub_questions],
        "answers": [_answer_to_dict(item) for item in answers],
        "knowledge_points": [
            {
                "kp_id": item.knowledge_point_id,
                "is_primary": item.is_primary,
                "weight": item.weight,
            }
            for item in knowledge
        ],
        "media_items": media_items,
    }


@router.patch("/{question_id}", response_model=IdResponse)
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdResponse:
    """单事务聚合更新题目（包含主表、小问、多空答案、知识点和媒体关联）。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")

    raw_data = payload.model_dump(exclude_unset=True)
    has_subs = "sub_questions" in raw_data
    has_answers = "answers" in raw_data
    has_kps = "knowledge_points" in raw_data
    has_media = "media_items" in raw_data

    subs_data = raw_data.pop("sub_questions", None)
    answers_data = raw_data.pop("answers", None)
    kps_data = raw_data.pop("knowledge_points", None)
    media_data = raw_data.pop("media_items", None)

    # 1. 预校验
    if has_kps and payload.knowledge_points is not None:
        _validate_knowledge_points(session, payload.knowledge_points)
    if has_media and payload.media_items is not None:
        _validate_media_items(session, payload.media_items)

    # 2. 更新主表标量字段
    for field, value in raw_data.items():
        setattr(question, field, value)

    # 3. 重新计算 Checksum
    if "stem" in raw_data or "options" in raw_data:
        question.checksum = compute_question_checksum(question.stem, question.options)

    question.updated_at = utc_now()
    session.add(question)

    # 4. 更新小问（全量替换）
    if has_subs and subs_data is not None:
        old_subs = session.exec(
            select(SubQuestion).where(SubQuestion.question_id == question_id)
        ).all()
        for old in old_subs:
            session.delete(old)
        session.flush()
        for index, sub in enumerate(subs_data):
            session.add(
                SubQuestion(
                    question_id=question_id,
                    label=sub.get("label") or f"({index + 1})",
                    stem=sub.get("stem"),
                    score=sub.get("score", 0.0),
                    answer=sub.get("answer"),
                    analysis=sub.get("analysis"),
                    display_order=sub.get("display_order", index),
                )
            )

    # 5. 更新多空答案（全量替换）
    if has_answers and answers_data is not None:
        old_ans = session.exec(
            select(QuestionAnswer).where(QuestionAnswer.question_id == question_id)
        ).all()
        for old in old_ans:
            session.delete(old)
        session.flush()
        for ans in answers_data:
            session.add(
                QuestionAnswer(
                    question_id=question_id,
                    blank_index=ans.get("blank_index", 1),
                    answer_text=ans["answer_text"],
                    is_primary=ans.get("is_primary", True),
                    match_rule=ans.get("match_rule"),
                )
            )

    # 6. 更新知识点关联（全量替换）
    if has_kps and kps_data is not None:
        old_kps = session.exec(
            select(QuestionKnowledge).where(QuestionKnowledge.question_id == question_id)
        ).all()
        for old in old_kps:
            session.delete(old)
        session.flush()
        for kp in kps_data:
            session.add(
                QuestionKnowledge(
                    question_id=question_id,
                    knowledge_point_id=kp["kp_id"],
                    is_primary=kp.get("is_primary", False),
                    weight=kp.get("weight", 1.0),
                )
            )

    # 7. 更新媒体关联（全量替换并准确调整引用计数）
    if has_media and media_data is not None:
        old_qms = session.exec(
            select(QuestionMedia).where(QuestionMedia.question_id == question_id)
        ).all()
        old_media_ids = [qm.media_id for qm in old_qms]
        new_media_ids = [m["media_id"] for m in media_data]

        # 删旧
        for old in old_qms:
            session.delete(old)
        session.flush()

        # 计算引用计数增减量
        from collections import Counter

        old_counts = Counter(old_media_ids)
        new_counts = Counter(new_media_ids)
        all_affected = set(old_media_ids) | set(new_media_ids)

        for m_id in all_affected:
            diff = new_counts.get(m_id, 0) - old_counts.get(m_id, 0)
            if diff != 0:
                media_res = session.get(MediaResource, m_id)
                if media_res:
                    media_res.reference_count = max(0, media_res.reference_count + diff)
                    session.add(media_res)

        # 添新
        for index, med in enumerate(media_data):
            session.add(
                QuestionMedia(
                    question_id=question_id,
                    media_id=med["media_id"],
                    usage_type=med["usage_type"],
                    display_order=med.get("display_order", index),
                    alt_text=med.get("alt_text"),
                    caption=med.get("caption"),
                )
            )

    # 8. 记录审计并统一提交
    add_audit_event(
        session,
        action="update",
        resource_type="question",
        actor=current_user,
        resource_id=question.id,
        changes={"fields": sorted(raw_data)},
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
    """软删题目。已有试卷快照完全隔离保留不受影响。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    question.is_active = False
    question.updated_at = utc_now()
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


@router.post("/{question_id}/media", response_model=OkResponse)
def associate_question_media(
    question_id: int,
    payload: QuestionMediaAssociatePayload,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """为题目独立关联单个媒体资源并增加其引用计数。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")

    media = session.get(MediaResource, payload.media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="媒体不存在")

    existing = session.exec(
        select(QuestionMedia).where(
            QuestionMedia.question_id == question_id,
            QuestionMedia.media_id == payload.media_id,
            QuestionMedia.usage_type == payload.usage_type,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=422, detail="该媒体已在此用途下关联此题")

    qm = QuestionMedia(
        question_id=question_id,
        media_id=payload.media_id,
        usage_type=payload.usage_type,
        display_order=payload.display_order,
        alt_text=payload.alt_text,
        caption=payload.caption,
    )
    session.add(qm)
    media.reference_count += 1
    session.add(media)

    add_audit_event(
        session,
        action="associate_media",
        resource_type="question",
        actor=current_user,
        resource_id=question_id,
        changes={"media_id": payload.media_id, "usage_type": payload.usage_type},
        request=request,
    )
    session.commit()
    return OkResponse()


@router.delete("/{question_id}/media/{media_id}", response_model=OkResponse)
def disassociate_question_media(
    question_id: int,
    media_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """解除题目与媒体的关联并减少其引用计数。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")

    qms = session.exec(
        select(QuestionMedia).where(
            QuestionMedia.question_id == question_id,
            QuestionMedia.media_id == media_id,
        )
    ).all()
    if not qms:
        raise HTTPException(status_code=404, detail="未找到该关联")

    for qm in qms:
        session.delete(qm)

    media = session.get(MediaResource, media_id)
    if media:
        media.reference_count = max(0, media.reference_count - len(qms))
        session.add(media)

    add_audit_event(
        session,
        action="disassociate_media",
        resource_type="question",
        actor=current_user,
        resource_id=question_id,
        changes={"media_id": media_id, "removed_count": len(qms)},
        request=request,
    )
    session.commit()
    return OkResponse()


# ===== 保留向前兼容接口 =====


@router.put("/{question_id}/knowledge", response_model=ReplaceResponse)
def set_question_knowledge(
    question_id: int,
    payload: QuestionKnowledgeSet,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ReplaceResponse:
    """全量覆盖题目的知识点关联（向后兼容）。"""
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")

    _validate_knowledge_points(session, payload.items)

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
        changes={"knowledge_point_ids": [item.kp_id for item in payload.items]},
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
    """全量覆盖题目的小问（向后兼容）。"""
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
        "checksum": question.checksum,
        "created_at": question.created_at,
    }


def _sub_question_to_dict(sub_question: SubQuestion) -> dict:
    return {
        "id": sub_question.id,
        "label": sub_question.label,
        "stem": sub_question.stem,
        "score": sub_question.score,
        "answer": sub_question.answer,
        "analysis": sub_question.analysis,
        "display_order": sub_question.display_order,
    }


def _answer_to_dict(answer: QuestionAnswer) -> dict:
    return {
        "id": answer.id,
        "blank_index": answer.blank_index,
        "answer_text": answer.answer_text,
        "is_primary": answer.is_primary,
        "match_rule": answer.match_rule,
    }
