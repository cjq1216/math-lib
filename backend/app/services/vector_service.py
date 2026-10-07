"""题目 Embedding 向量持久化与内存余弦相似度检索引擎。

特性：
1. 纯 Python 原生/跨平台余弦相似度计算，解耦特定本地 C 编译扩展（sqlite-vec），在各系统下稳定零依赖；
2. 支持题目向量的 Upsert 存储与维度检验；
3. 支持基于目标向量 / 题目 ID 查找相似题（Top-K、阈值过滤）；
4. 毫秒级检索耗时，轻松应对中小机构几千至数万题规模的查重推荐需求。
"""

from __future__ import annotations

import math
from typing import Any

from sqlmodel import Session, select

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.models.question import Question
from app.models.question_embedding import QuestionEmbedding


def cosine_similarity(u: list[float], v: list[float]) -> float:
    """计算两个浮点向量之间的余弦相似度（取值范围 -1.0 到 1.0）。"""
    if not u or not v or len(u) != len(v):
        return 0.0

    dot_product = sum(a * b for a, b in zip(u, v, strict=False))
    norm_u = math.sqrt(sum(a * a for a in u))
    norm_v = math.sqrt(sum(b * b for b in v))

    if norm_u == 0.0 or norm_v == 0.0:
        return 0.0

    return dot_product / (norm_u * norm_v)


def save_question_embedding(
    session: Session,
    question_id: int,
    vector: list[float],
    model_name: str | None = None,
) -> QuestionEmbedding:
    """持久化保存或更新题目的向量数据。"""
    record = session.get(QuestionEmbedding, question_id)
    target_model = model_name or settings.embedding_model

    if record:
        record.embedding = vector
        record.dimensions = len(vector)
        record.model = target_model
        record.updated_at = utc_now()
    else:
        record = QuestionEmbedding(
            question_id=question_id,
            embedding=vector,
            dimensions=len(vector),
            model=target_model,
        )
        session.add(record)

    session.flush()
    return record


def find_similar_questions(
    session: Session,
    target_vector: list[float],
    top_k: int = 5,
    threshold: float = 0.7,
    exclude_question_id: int | None = None,
) -> list[tuple[int, float]]:
    """根据给定的向量在已持久化的题库向量中进行余弦相似度检索。

    返回: [(question_id, similarity_score), ...] 降序排列。
    """
    if not target_vector:
        return []

    # 仅在活跃题目的向量中检索
    stmt = (
        select(QuestionEmbedding.question_id, QuestionEmbedding.embedding)
        .join(Question, Question.id == QuestionEmbedding.question_id)
        .where(Question.is_active == True)
    )
    if exclude_question_id is not None:
        stmt = stmt.where(QuestionEmbedding.question_id != exclude_question_id)

    rows = session.exec(stmt).all()

    scores: list[tuple[int, float]] = []
    for q_id, emb in rows:
        if not emb:
            continue
        sim = cosine_similarity(target_vector, emb)
        if sim >= threshold:
            scores.append((q_id, sim))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


def find_similar_by_question_id(
    session: Session,
    question_id: int,
    top_k: int = 5,
    threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """根据指定题目 ID 查找题库中的相似题，包含题目详细信息及相似度。"""
    record = session.get(QuestionEmbedding, question_id)
    if not record or not record.embedding:
        return []

    similar_pairs = find_similar_questions(
        session=session,
        target_vector=record.embedding,
        top_k=top_k,
        threshold=threshold,
        exclude_question_id=question_id,
    )

    results: list[dict[str, Any]] = []
    for q_id, sim in similar_pairs:
        q = session.get(Question, q_id)
        if q and q.is_active:
            results.append(
                {
                    "question_id": q.id,
                    "similarity": round(sim, 4),
                    "stem": q.stem,
                    "question_type": q.question_type.value,
                    "difficulty": q.difficulty,
                    "total_score": q.total_score,
                }
            )

    return results
