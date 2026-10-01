"""智能组卷引擎（四步拆分架构）。

流程规范：
1. plan（预检）：
   - 过滤有效题目与禁含知识点；
   - 统计各题型、难度及必含知识点可用题量；
   - 预检硬约束是否可满足，若不可满足抛出 ConstraintUnsatisfiableError，包含明确结构化缺失原因；
2. generate（选题）：
   - 支持固定随机种子（seed）以实现复现；
   - 优先在对应题型内选择必含知识点题目（兼顾禁含与全局去重）；
   - 按难度分布比例分桶抽取题目；
   - 严格全局去重，候选不足时仅在同题型邻近难度中补充，绝不产生重复题；
3. validate（复核）：
   - 卷内题目 ID 全局唯一（0 重复）；
   - 各题型数量 100% 符合设定；
   - 必含知识点 100% 覆盖；
   - 禁含知识点 0 违规；
   - 复核失败绝不保存残卷；
4. persist（持久化）：
   - 支持按题型赋分（type_scores）或按设定总分分摊；
   - 自动生成大题中文区段（如 一、单项选择题，二、填空题 等）；
   - 写入 Paper 主表及 PaperQuestion 快照（题干、答案、解析、选项）。
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Any

from sqlmodel import Session, select

from app.models.paper import Paper, PaperQuestion, PaperStatus
from app.models.question import Question, QuestionKnowledge, QuestionType


class ConstraintUnsatisfiableError(Exception):
    """组卷约束无法满足异常，携带结构化缺失详情。"""

    def __init__(
        self,
        message: str,
        missing_types: dict[str, dict[str, int]] | None = None,
        missing_required_kps: list[int] | None = None,
        detail_dict: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.missing_types = missing_types or {}
        self.missing_required_kps = missing_required_kps or []
        self.detail_dict = detail_dict or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "constraint_unsatisfiable",
            "message": self.message,
            "missing_types": self.missing_types,
            "missing_required_kps": self.missing_required_kps,
            **self.detail_dict,
        }


SECTION_NAMES: dict[str, str] = {
    QuestionType.CHOICE_SINGLE.value: "一、单项选择题",
    QuestionType.CHOICE_MULTI.value: "二、多项选择题",
    QuestionType.FILL.value: "三、填空题",
    QuestionType.JUDGE.value: "四、判断题",
    QuestionType.SOLUTION.value: "五、解答题",
    QuestionType.PROOF.value: "六、证明题",
}

SECTION_SORT_ORDER: dict[str, int] = {
    QuestionType.CHOICE_SINGLE.value: 1,
    QuestionType.CHOICE_MULTI.value: 2,
    QuestionType.FILL.value: 3,
    QuestionType.JUDGE.value: 4,
    QuestionType.SOLUTION.value: 5,
    QuestionType.PROOF.value: 6,
}


def plan_paper_generation(session: Session, constraint: dict[str, Any]) -> dict[str, Any]:
    """第一阶段：统计可用候选并预检硬约束。若无法满足则提前报错。"""
    type_dist = constraint.get("type_distribution", {})
    difficulty_ratio = constraint.get("difficulty_ratio", {})
    required_kps = list(constraint.get("required_kps", []))
    forbidden_kps = list(constraint.get("forbidden_kps", []))

    # 1. 题型参数基础校验
    valid_qtypes = {e.value for e in QuestionType}
    requested_types = {t: int(c) for t, c in type_dist.items() if t in valid_qtypes and int(c) > 0}
    if not requested_types:
        raise ConstraintUnsatisfiableError("组卷必须至少指定一种题型及其数量")

    # 2. 查询题库中未被禁用的题目
    stmt = select(Question).where(
        Question.is_active == True,
        Question.question_type.in_([QuestionType(t) for t in requested_types.keys()]),
    )
    all_qs = session.exec(stmt).all()

    # 3. 关联知识点并过滤禁含知识点
    q_ids = [q.id for q in all_qs]
    q_to_kps: dict[int, set[int]] = {q.id: set() for q in all_qs}
    if q_ids:
        qk_rows = session.exec(
            select(QuestionKnowledge.question_id, QuestionKnowledge.knowledge_point_id).where(
                QuestionKnowledge.question_id.in_(q_ids)
            )
        ).all()
        for q_id, kp_id in qk_rows:
            q_to_kps[q_id].add(kp_id)

    # 过滤包含禁含知识点的题目
    forbidden_set = set(forbidden_kps)
    available_qs = [q for q in all_qs if not (q_to_kps.get(q.id, set()) & forbidden_set)]

    # 4. 按 (题型, 难度) 分桶
    buckets: dict[tuple[str, int], list[Question]] = {}
    type_available_counts: dict[str, int] = {t: 0 for t in requested_types}
    for q in available_qs:
        qt = q.question_type.value
        key = (qt, q.difficulty)
        buckets.setdefault(key, []).append(q)
        if qt in type_available_counts:
            type_available_counts[qt] += 1

    # 5. 校验各题型总题量是否足够
    missing_types: dict[str, dict[str, int]] = {}
    for qt, needed in requested_types.items():
        avail = type_available_counts.get(qt, 0)
        if avail < needed:
            missing_types[qt] = {
                "needed": needed,
                "available": avail,
                "shortage": needed - avail,
            }

    # 6. 校验每个必含知识点是否至少在候选库中存在未被禁含的题目
    missing_required_kps: list[int] = []
    for rkp in required_kps:
        has_cand = any(rkp in q_to_kps.get(q.id, set()) for q in available_qs)
        if not has_cand:
            missing_required_kps.append(rkp)

    if missing_types or missing_required_kps:
        error_reasons = []
        if missing_types:
            for qt, info in missing_types.items():
                error_reasons.append(
                    f"题型[{qt}]题量不足（需要 {info['needed']} 题，当前仅可用 {info['available']} 题，缺少 {info['shortage']} 题）"
                )
        if missing_required_kps:
            error_reasons.append(
                f"必含知识点 ID {missing_required_kps} 在当前可用题库（已剔除禁含知识点）中无任何可用题目"
            )
        raise ConstraintUnsatisfiableError(
            message="; ".join(error_reasons),
            missing_types=missing_types,
            missing_required_kps=missing_required_kps,
        )

    return {
        "requested_types": requested_types,
        "difficulty_ratio": difficulty_ratio,
        "required_kps": required_kps,
        "forbidden_kps": forbidden_kps,
        "available_qs": available_qs,
        "buckets": buckets,
        "q_to_kps": q_to_kps,
    }


def generate_paper_questions(
    plan_data: dict[str, Any],
    seed: int | None = None,
) -> list[Question]:
    """第二阶段：按硬约束与难度比例抽题，严格全局去重。"""
    rng = random.Random(seed) if seed is not None else random.Random()

    requested_types: dict[str, int] = plan_data["requested_types"]
    difficulty_ratio: dict[str, float] = plan_data["difficulty_ratio"]
    required_kps: list[int] = plan_data["required_kps"]
    available_qs: list[Question] = plan_data["available_qs"]
    q_to_kps: dict[int, set[int]] = plan_data["q_to_kps"]

    selected_questions: list[Question] = []
    picked_ids: set[int] = set()
    picked_type_counts: dict[str, int] = {t: 0 for t in requested_types}

    # Step A: 优先覆盖必含知识点（必须在有额度的题型内挑选，避免破坏题型配比）
    uncovered_required = set(required_kps)
    for rkp in list(uncovered_required):
        if rkp not in uncovered_required:
            continue
        # 寻找覆盖 rkp 且题型仍有剩余名额的候选
        cands = [
            q
            for q in available_qs
            if q.id not in picked_ids
            and rkp in q_to_kps.get(q.id, set())
            and picked_type_counts[q.question_type.value] < requested_types[q.question_type.value]
        ]
        if cands:
            # 优先挑覆盖其他未覆盖必含知识点较多的题
            cands.sort(
                key=lambda q: len(q_to_kps.get(q.id, set()) & uncovered_required),
                reverse=True,
            )
            # 在最佳覆盖候选池中随机挑一个
            best_overlap = len(q_to_kps.get(cands[0].id, set()) & uncovered_required)
            best_pool = [
                q
                for q in cands
                if len(q_to_kps.get(q.id, set()) & uncovered_required) == best_overlap
            ]
            picked = rng.choice(best_pool)

            selected_questions.append(picked)
            picked_ids.add(picked.id)
            picked_type_counts[picked.question_type.value] += 1
            uncovered_required -= q_to_kps.get(picked.id, set())

    # Step B: 补充各题型所需题量（按难度分布比例抽题）
    for qtype, needed_total in requested_types.items():
        already_picked = picked_type_counts[qtype]
        remaining_needed = needed_total - already_picked
        if remaining_needed <= 0:
            continue

        # 计算当前题型在各难度下的目标分配数
        diff_targets = _distribute_difficulty_counts(remaining_needed, difficulty_ratio)

        # 在当前题型中找所有未选题目并按难度归类
        type_pool = [
            q
            for q in available_qs
            if q.question_type.value == qtype and q.id not in picked_ids
        ]
        type_diff_map: dict[int, list[Question]] = {d: [] for d in range(1, 6)}
        for q in type_pool:
            type_diff_map[q.difficulty].append(q)

        for d in range(1, 6):
            rng.shuffle(type_diff_map[d])

        # 按难度抽取
        for d, count in diff_targets.items():
            if count <= 0:
                continue
            pool = type_diff_map[d]
            take = min(count, len(pool))
            for _ in range(take):
                item = pool.pop()
                selected_questions.append(item)
                picked_ids.add(item.id)
                picked_type_counts[qtype] += 1

        # 若某些难度题目不足导致本题型仍有缺口，在同题型的其他难度中补齐
        current_type_count = picked_type_counts[qtype]
        if current_type_count < needed_total:
            shortage = needed_total - current_type_count
            remaining_type_candidates = [
                q
                for q in available_qs
                if q.question_type.value == qtype and q.id not in picked_ids
            ]
            rng.shuffle(remaining_type_candidates)
            take = min(shortage, len(remaining_type_candidates))
            for i in range(take):
                item = remaining_type_candidates[i]
                selected_questions.append(item)
                picked_ids.add(item.id)
                picked_type_counts[qtype] += 1

    return selected_questions


def validate_paper_selection(
    selected: list[Question],
    constraint: dict[str, Any],
    plan_data: dict[str, Any],
) -> None:
    """第三阶段：生成后复核硬约束（去重、题型数量、必含、禁含）。"""
    # 1. 唯一性复核（0 重复）
    selected_ids = [q.id for q in selected]
    if len(selected_ids) != len(set(selected_ids)):
        raise ConstraintUnsatisfiableError("组卷复核失败：题目存在卷内重复")

    # 2. 题型数量复核
    actual_type_counts = Counter(q.question_type.value for q in selected)
    requested_types: dict[str, int] = plan_data["requested_types"]
    for qt, needed in requested_types.items():
        actual = actual_type_counts.get(qt, 0)
        if actual != needed:
            raise ConstraintUnsatisfiableError(
                f"组卷复核失败：题型[{qt}]数量未达标（要求 {needed} 题，实际选中 {actual} 题）"
            )

    # 3. 禁含知识点复核
    q_to_kps = plan_data["q_to_kps"]
    forbidden_set = set(plan_data["forbidden_kps"])
    for q in selected:
        violated = q_to_kps.get(q.id, set()) & forbidden_set
        if violated:
            raise ConstraintUnsatisfiableError(
                f"组卷复核失败：题目 #{q.id} 包含了禁含知识点 {list(violated)}"
            )

    # 4. 必含知识点复核
    covered_kps = set()
    for q in selected:
        covered_kps.update(q_to_kps.get(q.id, set()))
    missing_required = set(plan_data["required_kps"]) - covered_kps
    if missing_required:
        raise ConstraintUnsatisfiableError(
            f"组卷复核失败：必含知识点未被全部覆盖，缺失: {list(missing_required)}"
        )


def persist_generated_paper(
    session: Session,
    title: str,
    constraint: dict[str, Any],
    selected: list[Question],
    created_by: int | None = None,
    score_strategy: dict[str, float] | None = None,
) -> tuple[Paper, list[PaperQuestion]]:
    """第四阶段：计算分值、分大题段落并保存试卷与快照。"""
    total_score = float(constraint.get("total_score", 100.0))
    duration_minutes = int(constraint.get("duration_minutes", 90))
    type_scores = score_strategy or constraint.get("type_scores") or {}

    # 按大题标准顺序排序：选择题 -> 填空题 -> 解答题，同一大题内按难度升序排序
    def _sort_key(q: Question) -> tuple[int, int, int]:
        order = SECTION_SORT_ORDER.get(q.question_type.value, 99)
        return (order, q.difficulty, q.id or 0)

    sorted_selected = sorted(selected, key=_sort_key)

    # 分配单题分数
    total_questions = len(sorted_selected)
    scores: list[float] = []

    if type_scores:
        for q in sorted_selected:
            scores.append(float(type_scores.get(q.question_type.value, 5.0)))
        total_score = sum(scores)
    else:
        # 按总分平摊并保证总和精确等于设定总分
        if total_questions > 0:
            base_score = round(total_score / total_questions, 1)
            scores = [base_score] * total_questions
            # 补齐微小尾数误差在最后一题上
            scores[-1] = round(total_score - sum(scores[:-1]), 1)
        else:
            scores = []

    # 1. 保存 Paper 主表
    paper = Paper(
        title=title,
        total_score=total_score,
        duration_minutes=duration_minutes,
        constraint_json=constraint,
        status=PaperStatus.DRAFT,
        question_count=total_questions,
        created_by=created_by,
    )
    session.add(paper)
    session.flush()

    # 2. 保存 PaperQuestion（包含快照字段）
    pq_list: list[PaperQuestion] = []
    for order, (q, s) in enumerate(zip(sorted_selected, scores, strict=False), start=1):
        section_name = SECTION_NAMES.get(q.question_type.value, "其他题型")
        pq = PaperQuestion(
            paper_id=paper.id,
            question_id=q.id,
            section=section_name,
            display_order=order,
            score=s,
            stem_snapshot=q.stem,
            answer_snapshot=q.answer,
            analysis_snapshot=q.analysis,
            options_snapshot=q.options,
        )
        session.add(pq)
        pq_list.append(pq)

    session.flush()
    return paper, pq_list


def generate_paper(
    session: Session,
    title: str,
    constraint: dict[str, Any],
    created_by: int | None = None,
    seed: int | None = None,
    score_strategy: dict[str, float] | None = None,
) -> tuple[Paper, list[PaperQuestion]]:
    """四步拆分主入口函数。"""
    # 1. plan
    plan_data = plan_paper_generation(session, constraint)

    # 2. generate
    selected = generate_paper_questions(plan_data, seed=seed)

    # 3. validate
    validate_paper_selection(selected, constraint, plan_data)

    # 4. persist
    return persist_generated_paper(
        session=session,
        title=title,
        constraint=constraint,
        selected=selected,
        created_by=created_by,
        score_strategy=score_strategy,
    )


def _distribute_difficulty_counts(
    total: int, ratio_dict: dict[str, float]
) -> dict[int, int]:
    """根据难度比例分配题数。"""
    if total <= 0:
        return {}
    if not ratio_dict:
        return {3: total}

    counts: dict[int, int] = {}
    allocated = 0
    # 按比例倒序计算
    sorted_ratios = sorted(
        ratio_dict.items(), key=lambda x: float(x[1]), reverse=True
    )
    for d_str, ratio in sorted_ratios:
        d = int(d_str)
        c = int(round(total * float(ratio)))
        counts[d] = c
        allocated += c

    diff = total - allocated
    if diff != 0 and counts:
        first_key = next(iter(counts))
        counts[first_key] = max(0, counts[first_key] + diff)

    return {k: v for k, v in counts.items() if v > 0}
