"""
学情分析表

聚合学生各知识点掌握度 + 薄弱点识别
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class StudentKPStats(SQLModel, table=True):
    """
    学生知识点掌握度

    每条记录：(学生, 知识点) → 当前掌握度
    通过分析 homework_results 自动聚合更新
    """

    __tablename__ = "student_kp_stats"

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="students.id", index=True, ondelete="CASCADE")
    knowledge_point_id: int = Field(foreign_key="knowledge_points.id", index=True)

    # 统计
    total_attempts: int = Field(default=0, description="累计作答次数")
    correct_count: int = Field(default=0, description="正确次数")
    accuracy: float = Field(default=0.0, description="正确率 0.0-1.0")

    # 难度加权（高分题正确更有价值）
    weighted_score: float = Field(default=0.0)

    # 趋势
    recent_5_accuracy: Optional[float] = Field(default=None, description="最近5次正确率")
    trend: Optional[str] = Field(default=None, max_length=16, description="up/down/stable")

    # 时间
    last_practiced_at: Optional[datetime] = Field(default=None)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)


class WeakPoint(SQLModel, table=True):
    """
    薄弱知识点识别结果

    系统定期扫描，标记需要重点练习的 (学生, 知识点) 组合
    """

    __tablename__ = "weak_points"

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="students.id", index=True, ondelete="CASCADE")
    knowledge_point_id: int = Field(foreign_key="knowledge_points.id", index=True)

    # 评估
    accuracy: float = Field(default=0.0, description="正确率")
    attempts: int = Field(default=0, description="作答次数")
    severity: str = Field(default="medium", max_length=16, description="low/medium/high")

    # 推荐练习题数
    recommended_practice_count: int = Field(default=5)

    # 状态
    is_resolved: bool = Field(default=False, description="是否已攻克")
    resolved_at: Optional[datetime] = Field(default=None)

    detected_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
