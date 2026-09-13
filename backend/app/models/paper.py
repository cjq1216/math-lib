"""
试卷表 + 试卷-题目关联（含快照）

关键设计：题目改了不影响已出过的卷子。
paper_questions 中存 stem/answer/analysis 快照。
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import JSON, Field, SQLModel


class PaperStatus(str, Enum):
    """试卷状态"""

    DRAFT = "draft"             # 草稿
    PUBLISHED = "published"     # 已发布
    ARCHIVED = "archived"       # 已归档


class Paper(SQLModel, table=True):
    """试卷主表"""

    __tablename__ = "papers"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(max_length=255, index=True)
    description: Optional[str] = Field(default=None)

    total_score: float = Field(default=100.0)
    duration_minutes: int = Field(default=90, description="作答时长")

    status: PaperStatus = Field(default=PaperStatus.DRAFT)

    # 组卷约束（保存为快照）
    # 格式：{"type_distribution": {...}, "difficulty_ratio": {...}, "required_kps": [...]}
    constraint_json: Optional[dict] = Field(default=None, sa_type=JSON)

    # 标签
    grade: Optional[int] = Field(default=None)
    semester: Optional[str] = Field(default=None, max_length=16)
    tags: Optional[list[str]] = Field(default=None, sa_type=JSON)

    # 来源
    is_template: bool = Field(default=False, description="是否为模板")
    parent_template_id: Optional[int] = Field(default=None, foreign_key="papers.id")

    # 统计
    question_count: int = Field(default=0)
    used_count: int = Field(default=0, description="被使用次数")

    notes: Optional[str] = Field(default=None)
    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: Optional[datetime] = Field(default=None)


class PaperQuestion(SQLModel, table=True):
    """
    试卷-题目关联（含快照）

    关键点：保存 stem/answer/analysis 三个快照字段
    当原题改了，历史卷不受影响。
    """

    __tablename__ = "paper_questions"

    id: Optional[int] = Field(default=None, primary_key=True)
    paper_id: int = Field(foreign_key="papers.id", index=True, ondelete="CASCADE")
    question_id: int = Field(foreign_key="questions.id", index=True)

    # 位置信息
    section: Optional[str] = Field(default=None, max_length=16, description="大题号 I/II/III")
    display_order: int = Field(default=0, description="题号")

    # 分值
    score: float = Field(default=10.0)

    # ===== 快照字段 =====
    stem_snapshot: str = Field(description="题干快照")
    answer_snapshot: Optional[str] = Field(default=None)
    analysis_snapshot: Optional[str] = Field(default=None)
    options_snapshot: Optional[list[str]] = Field(default=None, sa_type=JSON)

    created_at: datetime = Field(default_factory=datetime.utcnow)
