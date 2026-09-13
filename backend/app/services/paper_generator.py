"""
智能组卷引擎

实现规划文档 §6.7.3：分层贪心 + 知识点约束检查

输入约束：
- 总分
- 难度分布（如 易30%/中50%/难20%）
- 题型配比
- 必含/禁含知识点
- 作答时间

输出：
- Paper + PaperQuestion（含快照）
"""
import random
from typing import Any

from sqlmodel import Session, select

from app.models.paper import Paper, PaperQuestion, PaperStatus
from app.models.question import Question, QuestionKnowledge, QuestionType


def generate_paper(
    session: Session,
    title: str,
    constraint: dict[str, Any],
    created_by: int | None = None,
) -> tuple[Paper, list[PaperQuestion]]:
    """
    主入口

    constraint:
    {
        "total_score": 100,
        "duration_minutes": 120,
        "type_distribution": {"choice_single": 20, "fill": 10, "solution": 5},
        "difficulty_ratio": {"1": 0.2, "2": 0.3, "3": 0.3, "4": 0.15, "5": 0.05},
        "required_kps": [101, 102],  # 必含知识点
        "forbidden_kps": [205],       # 禁含知识点
    }
    """
    # 1. 创建 Paper
    paper = Paper(
        title=title,
        total_score=float(constraint.get("total_score", 100)),
        duration_minutes=int(constraint.get("duration_minutes", 90)),
        constraint_json=constraint,
        status=PaperStatus.DRAFT,
        created_by=created_by,
    )
    session.add(paper)
    session.flush()

    # 2. 按题型+难度分桶
    buckets = _build_buckets(
        session,
        type_dist=constraint.get("type_distribution", {}),
        difficulty_ratio=constraint.get("difficulty_ratio", {}),
        forbidden_kps=constraint.get("forbidden_kps", []),
    )

    # 3. 按题型贪心抽取
    selected: list[Question] = []
    for qtype, type_count in constraint.get("type_distribution", {}).items():
        diff_counts = _distribute_difficulty(
            type_count, constraint.get("difficulty_ratio", {})
        )
        for diff, count in diff_counts.items():
            candidates = buckets.get((qtype, diff), [])
            if len(candidates) < count:
                # 候选不足，降低难度补
                candidates = _expand_candidates(buckets, qtype, diff, count)
            picked = random.sample(candidates, min(count, len(candidates)))
            selected.extend(picked)

    # 4. 必含知识点校验
    selected = _ensure_required_kps(session, selected, constraint.get("required_kps", []))

    # 5. 分配分值（使总分达标）
    score_per_question = paper.total_score / max(len(selected), 1)

    # 6. 生成 PaperQuestion（含快照）
    pq_list = []
    for order, q in enumerate(selected, start=1):
        pq = PaperQuestion(
            paper_id=paper.id,
            question_id=q.id,
            display_order=order,
            score=score_per_question,
            stem_snapshot=q.stem,
            answer_snapshot=q.answer,
            analysis_snapshot=q.analysis,
            options_snapshot=q.options,
        )
        session.add(pq)
        pq_list.append(pq)

    # 7. 更新 paper 统计
    paper.question_count = len(selected)

    session.commit()
    return paper, pq_list


def _build_buckets(
    session: Session,
    type_dist: dict[str, int],
    difficulty_ratio: dict[str, float],
    forbidden_kps: list[int],
) -> dict[tuple[str, int], list[Question]]:
    """按 (题型, 难度) 分桶"""
    # 找出需要的题型和难度
    qtypes = [QuestionType(t) for t in type_dist.keys() if t in [e.value for e in QuestionType]]
    difficulties = [int(d) for d in difficulty_ratio.keys()]

    if not qtypes:
        return {}

    stmt = select(Question).where(
        Question.is_active == True,
        Question.question_type.in_(qtypes),
        Question.difficulty.in_(difficulties),
    )

    questions = session.exec(stmt).all()

    # 过滤禁含知识点
    if forbidden_kps:
        forbidden_q_ids = set(
            session.exec(
                select(QuestionKnowledge.question_id).where(
                    QuestionKnowledge.knowledge_point_id.in_(forbidden_kps)
                )
            ).all()
        )
        questions = [q for q in questions if q.id not in forbidden_q_ids]

    # 分桶
    buckets: dict[tuple[str, int], list[Question]] = {}
    for q in questions:
        key = (q.question_type.value, q.difficulty)
        buckets.setdefault(key, []).append(q)

    return buckets


def _distribute_difficulty(
    total_count: int, difficulty_ratio: dict[str, float]
) -> dict[int, int]:
    """按难度比例分配题目数"""
    if not difficulty_ratio or total_count <= 0:
        return {3: total_count}

    counts: dict[int, int] = {}
    allocated = 0
    for diff_str, ratio in sorted(difficulty_ratio.items(), key=lambda x: float(x[1]), reverse=True):
        diff = int(diff_str)
        c = int(round(total_count * float(ratio)))
        counts[diff] = c
        allocated += c

    # 调整误差
    diff = total_count - allocated
    if diff != 0 and counts:
        first_key = next(iter(counts))
        counts[first_key] = max(0, counts[first_key] + diff)

    return {k: v for k, v in counts.items() if v > 0}


def _expand_candidates(
    buckets: dict[tuple[str, int], list[Question]],
    qtype: str,
    target_diff: int,
    needed: int,
) -> list[Question]:
    """候选不足时，扩大难度范围"""
    pool = []
    for (qt, d), qs in buckets.items():
        if qt == qtype:
            pool.extend(qs)
    return pool


def _ensure_required_kps(
    session: Session,
    selected: list[Question],
    required_kps: list[int],
) -> list[Question]:
    """确保必含知识点被覆盖"""
    if not required_kps:
        return selected

    # 当前已覆盖的知识点
    selected_ids = [q.id for q in selected]
    covered_kps = set()
    if selected_ids:
        covered_kps = set(
            session.exec(
                select(QuestionKnowledge.knowledge_point_id).where(
                    QuestionKnowledge.question_id.in_(selected_ids)
                )
            ).all()
        )

    # 找出未覆盖的必含知识点
    missing = [kp for kp in required_kps if kp not in covered_kps]
    if not missing:
        return selected

    # 为每个缺失的必含知识点找替换题
    for kp_id in missing:
        # 候选：包含此知识点 且 不在已选
        candidate_qs = session.exec(
            select(Question)
            .join(QuestionKnowledge, QuestionKnowledge.question_id == Question.id)
            .where(QuestionKnowledge.knowledge_point_id == kp_id)
            .where(Question.is_active == True)
            .where(~Question.id.in_(selected_ids))
        ).all()

        if not candidate_qs:
            continue

        # 替换：去掉当前最弱的（不在必含知识点的）
        weakest_idx = -1
        weakest_kp_overlap = float("inf")
        for idx, q in enumerate(selected):
            if not selected_ids or idx >= len(selected_ids):
                continue
            q_kps = set(
                session.exec(
                    select(QuestionKnowledge.knowledge_point_id).where(
                        QuestionKnowledge.question_id == q.id
                    )
                ).all()
            )
            overlap = len(q_kps & set(required_kps))
            if overlap < weakest_kp_overlap:
                weakest_kp_overlap = overlap
                weakest_idx = idx

        if weakest_idx >= 0:
            selected[weakest_idx] = candidate_qs[0]
            selected_ids[weakest_idx] = candidate_qs[0].id

    return selected
