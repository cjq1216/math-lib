"""
题目表 - 核心结构化题库
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import JSON, Field, SQLModel


class QuestionType(str, Enum):
    """题目类型"""

    CHOICE_SINGLE = "choice_single"  # 单选
    CHOICE_MULTI = "choice_multi"  # 多选
    FILL = "fill"  # 填空
    JUDGE = "judge"  # 判断
    SOLUTION = "solution"  # 解答题
    PROOF = "proof"  # 证明题


class Question(SQLModel, table=True):
    """题目主表"""

    __tablename__ = "questions"

    id: Optional[int] = Field(default=None, primary_key=True)

    # ===== 题面 =====
    stem: str = Field(description="题干，LaTeX/Markdown")
    stem_html: Optional[str] = Field(default=None, description="渲染后 HTML（缓存）")

    # 选项（选择题用，JSON 列表）
    # 格式：["A. xxx", "B. xxx", ...]
    options: Optional[list[str]] = Field(default=None, sa_type=JSON)

    question_type: QuestionType = Field(default=QuestionType.CHOICE_SINGLE, index=True)
    difficulty: int = Field(default=3, ge=1, le=5, description="难度 1-5")

    # ===== 分值 =====
    total_score: float = Field(default=10.0, description="题目总分")
    default_score: Optional[float] = Field(default=None, description="每空/每问分数")

    # ===== 答案与解析 =====
    answer: Optional[str] = Field(default=None, description="主答案")
    analysis: Optional[str] = Field(default=None, description="解析")
    solution_steps: Optional[list[dict]] = Field(default=None, sa_type=JSON, description="解答步骤")

    # ===== 来源 =====
    source_id: Optional[int] = Field(default=None, foreign_key="sources.id")
    source_page: Optional[int] = Field(default=None)
    source_question_no: Optional[str] = Field(default=None, max_length=32)

    # ===== 去重 =====
    checksum: Optional[str] = Field(default=None, max_length=64, index=True)
    # Embedding 存在 question_embeddings 表；可选相似度索引在后续迭代接入。

    # ===== 元数据 =====
    tags: Optional[list[str]] = Field(default=None, sa_type=JSON, description="额外标签")
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False, description="是否经过人工校对")

    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SubQuestion(SQLModel, table=True):
    """
    复合题的小问（独立入库）

    例如：解答题"解方程 (1) ... (2) ... (3) ..."
    每个 (1)(2)(3) 作为一条 sub_question，能独立给分、独立聚合
    """

    __tablename__ = "sub_questions"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: int = Field(foreign_key="questions.id", index=True, ondelete="CASCADE")

    label: str = Field(max_length=16, description="标签，如 (1) (2) 第一问")
    stem: Optional[str] = Field(default=None, description="小问题干")
    score: float = Field(default=0.0, description="本小问分数")

    display_order: int = Field(default=0)
    answer: Optional[str] = Field(default=None, description="本小问答案")
    analysis: Optional[str] = Field(default=None, description="本小问解析")


class QuestionAnswer(SQLModel, table=True):
    """
    题目答案（多空独立 + 等价规则）

    一道填空题可能有多个空，每个空独立存一条。
    支持等价规则（正则/多种写法）。
    """

    __tablename__ = "question_answers"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: int = Field(foreign_key="questions.id", index=True, ondelete="CASCADE")
    sub_question_id: Optional[int] = Field(
        default=None, foreign_key="sub_questions.id", index=True, ondelete="CASCADE"
    )

    blank_index: int = Field(default=1, description="空号 1/2/3...")
    answer_text: str = Field(description="答案文本")
    is_primary: bool = Field(default=True, description="是否首选答案")

    # 等价规则（JSON）
    # 格式：{"regex": "\\s*", "allow_set": ["1/2", "0.5"]}
    match_rule: Optional[dict] = Field(default=None, sa_type=JSON)


class QuestionKnowledge(SQLModel, table=True):
    """题目-知识点关联表（N:M）"""

    __tablename__ = "question_knowledge"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: int = Field(foreign_key="questions.id", index=True, ondelete="CASCADE")
    knowledge_point_id: int = Field(foreign_key="knowledge_points.id", index=True)

    # 主知识点权重（用于学情分析加权）
    is_primary: bool = Field(default=False, description="是否主知识点")
    weight: float = Field(default=1.0, description="权重 0.0-1.0")

    created_at: datetime = Field(default_factory=datetime.utcnow)
