"""智能组卷算法单元测试与硬约束达标率验收。"""

from collections import Counter

import pytest
from sqlmodel import Session, select

from app.models.paper import Paper
from app.models.question import Question, QuestionKnowledge, QuestionType
from app.services.paper_generator import (
    ConstraintUnsatisfiableError,
    generate_paper,
)


def _seed_sample_questions(session: Session) -> dict[str, list[int]]:
    """向测试数据库插入一组结构化题目并打标。"""
    # 知识点 101, 102 为普通知识点；201 为禁含知识点
    created_ids: dict[str, list[int]] = {"choice_single": [], "fill": [], "solution": []}

    # 1. 单选 8 题 (难度 1-4 各 2 题)
    for i in range(8):
        diff = (i % 4) + 1
        q = Question(
            stem=f"单选题示例第 {i + 1} 题 $x={i}$",
            question_type=QuestionType.CHOICE_SINGLE,
            difficulty=diff,
            total_score=3.0,
            options=["A. 1", "B. 2", "C. 3", "D. 4"],
            answer="A",
            is_active=True,
        )
        session.add(q)
        session.flush()
        created_ids["choice_single"].append(q.id)

        # 前两题关联知识点 101，第三题关联禁含知识点 201
        if i < 2:
            session.add(QuestionKnowledge(question_id=q.id, knowledge_point_id=101, is_primary=True))
        elif i == 2:
            session.add(QuestionKnowledge(question_id=q.id, knowledge_point_id=201, is_primary=True))

    # 2. 填空 6 题 (难度 2-4 各 2 题)
    for i in range(6):
        diff = (i % 3) + 2
        q = Question(
            stem=f"填空题示例第 {i + 1} 题 $y={i}$",
            question_type=QuestionType.FILL,
            difficulty=diff,
            total_score=4.0,
            answer="5",
            is_active=True,
        )
        session.add(q)
        session.flush()
        created_ids["fill"].append(q.id)

        # 关联知识点 102
        if i < 2:
            session.add(QuestionKnowledge(question_id=q.id, knowledge_point_id=102, is_primary=True))

    # 3. 解答 4 题 (难度 3-5)
    for i in range(4):
        diff = i + 2
        q = Question(
            stem=f"解答题示例第 {i + 1} 题",
            question_type=QuestionType.SOLUTION,
            difficulty=diff,
            total_score=10.0,
            answer="过程略",
            is_active=True,
        )
        session.add(q)
        session.flush()
        created_ids["solution"].append(q.id)

    session.commit()
    return created_ids


def test_insufficient_candidates_raises_structured_error(test_engine):
    """测试候选题目不足时提前抛出结构化缺少原因，绝不保存残卷。"""
    with Session(test_engine) as session:
        _seed_sample_questions(session)

        # 当前题库只有 8 道单选题，请求 15 道单选
        constraint = {
            "type_distribution": {"choice_single": 15, "fill": 2},
            "difficulty_ratio": {"1": 0.5, "2": 0.5},
            "total_score": 100,
        }

        with pytest.raises(ConstraintUnsatisfiableError) as exc_info:
            generate_paper(session, title="题量不足测试卷", constraint=constraint)

        err = exc_info.value
        assert "choice_single" in err.missing_types
        assert err.missing_types["choice_single"]["needed"] == 15
        assert err.missing_types["choice_single"]["shortage"] > 0
        assert "题量不足" in err.message

        # 数据库中绝不残留残卷
        papers = session.exec(select(Paper)).all()
        assert len(papers) == 0


def test_missing_required_kp_raises_structured_error(test_engine):
    """测试必含知识点无可用题目时返回结构化错误。"""
    with Session(test_engine) as session:
        _seed_sample_questions(session)

        # 必含 999 知识点，但题库中没有任何题目关联 999
        constraint = {
            "type_distribution": {"choice_single": 3, "fill": 2},
            "required_kps": [999],
            "total_score": 50,
        }

        with pytest.raises(ConstraintUnsatisfiableError) as exc_info:
            generate_paper(session, title="必含缺失测试卷", constraint=constraint)

        err = exc_info.value
        assert 999 in err.missing_required_kps
        assert "必含知识点" in err.message


def test_forbidden_kps_strictly_excluded(test_engine):
    """测试禁含知识点被 100% 严格排除。"""
    with Session(test_engine) as session:
        _seed_sample_questions(session)

        # 题号 3 关联了禁含知识点 201，组卷时必须排除
        constraint = {
            "type_distribution": {"choice_single": 5, "fill": 3},
            "forbidden_kps": [201],
            "total_score": 100,
        }

        paper, pqs = generate_paper(session, title="禁含测试卷", constraint=constraint, seed=123)
        assert paper.id is not None
        assert len(pqs) == 8

        # 检查所有入选题目的知识点均不含 201
        for pq in pqs:
            kps = session.exec(
                select(QuestionKnowledge.knowledge_point_id).where(
                    QuestionKnowledge.question_id == pq.question_id
                )
            ).all()
            assert 201 not in kps


def test_hard_constraint_satisfaction_rate_100_percent(test_engine):
    """验证可满足条件下的硬约束达标率 100%（去重、题型数量、总分精确一致、必含覆盖）。"""
    with Session(test_engine) as session:
        _seed_sample_questions(session)

        constraint = {
            "type_distribution": {"choice_single": 4, "fill": 3, "solution": 2},
            "difficulty_ratio": {"1": 0.2, "2": 0.3, "3": 0.3, "4": 0.2},
            "required_kps": [101, 102],
            "forbidden_kps": [201],
            "total_score": 100.0,
            "duration_minutes": 100,
        }

        # 连续生成 10 次，验证 100% 达标
        for seed_idx in range(10):
            paper, pqs = generate_paper(
                session,
                title=f"达标率测试卷 #{seed_idx}",
                constraint=constraint,
                seed=seed_idx * 17 + 1,
            )

            # 1. 题量与题型配比 100% 达标
            assert len(pqs) == 9
            type_counts = Counter()
            q_ids = []
            for pq in pqs:
                q = session.get(Question, pq.question_id)
                type_counts[q.question_type.value] += 1
                q_ids.append(pq.question_id)

            assert type_counts["choice_single"] == 4
            assert type_counts["fill"] == 3
            assert type_counts["solution"] == 2

            # 2. 卷内 0 重复题目
            assert len(q_ids) == len(set(q_ids))

            # 3. 必含知识点 100% 覆盖
            covered_kps = set(
                session.exec(
                    select(QuestionKnowledge.knowledge_point_id).where(
                        QuestionKnowledge.question_id.in_(q_ids)
                    )
                ).all()
            )
            assert 101 in covered_kps
            assert 102 in covered_kps
            assert 201 not in covered_kps

            # 4. 单题分值之和精确等于试卷总分
            total_pq_score = sum(pq.score for pq in pqs)
            assert round(total_pq_score, 1) == 100.0


def test_seed_reproducibility(test_engine):
    """测试固定随机种子下组卷结果可完全精确复现。"""
    with Session(test_engine) as session:
        _seed_sample_questions(session)

        constraint = {
            "type_distribution": {"choice_single": 3, "fill": 2},
            "difficulty_ratio": {"2": 0.5, "3": 0.5},
            "total_score": 50,
        }

        p1, pqs1 = generate_paper(session, title="卷1", constraint=constraint, seed=999)
        p2, pqs2 = generate_paper(session, title="卷2", constraint=constraint, seed=999)

        ids1 = [pq.question_id for pq in pqs1]
        ids2 = [pq.question_id for pq in pqs2]
        assert ids1 == ids2


def test_type_scores_custom_strategy(test_engine):
    """测试按题型自定义赋分策略（单选3分，填空5分，解答10分）。"""
    with Session(test_engine) as session:
        _seed_sample_questions(session)

        constraint = {
            "type_distribution": {"choice_single": 3, "fill": 2, "solution": 1},
            "type_scores": {"choice_single": 3.0, "fill": 5.0, "solution": 12.0},
        }

        paper, pqs = generate_paper(session, title="自定义赋分测试卷", constraint=constraint)
        # 总分应自动按分值累计: 3*3 + 2*5 + 1*12 = 9 + 10 + 12 = 31分
        assert paper.total_score == 31.0
        for pq in pqs:
            q = session.get(Question, pq.question_id)
            if q.question_type == QuestionType.CHOICE_SINGLE:
                assert pq.score == 3.0
            elif q.question_type == QuestionType.FILL:
                assert pq.score == 5.0
            elif q.question_type == QuestionType.SOLUTION:
                assert pq.score == 12.0
