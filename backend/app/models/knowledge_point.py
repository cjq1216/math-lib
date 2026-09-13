"""
知识点表 - 树形结构（统一不分教材）
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class KnowledgePoint(SQLModel, table=True):
    """
    知识点表（树形结构）

    编号规则：G7-U1-S1 表示 七年级上-第1章-第1节
    树形深度：学段 → 学期 → 章 → 节 → 知识点
    """

    __tablename__ = "knowledge_points"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=32, unique=True, index=True, description="编号")
    name: str = Field(max_length=128, index=True, description="名称")
    parent_id: Optional[int] = Field(default=None, foreign_key="knowledge_points.id", index=True)

    # 学段
    grade: Optional[int] = Field(default=None, description="7/8/9")
    semester: Optional[str] = Field(default=None, max_length=16, description="上/下")

    # 层级
    chapter: Optional[str] = Field(default=None, max_length=64, description="章")
    section: Optional[str] = Field(default=None, max_length=64, description="节")

    # 难度提示
    difficulty_hint: Optional[int] = Field(default=None, ge=1, le=5)

    # 学科（预留扩展物理/化学）
    subject: str = Field(default="math", max_length=32, index=True)

    description: Optional[str] = Field(default=None, description="描述")
    display_order: int = Field(default=0, description="排序")

    is_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
