"""
学生信息表 - 教师代为维护，不登录系统
"""
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Student(SQLModel, table=True):
    """学生信息表"""

    __tablename__ = "students"

    id: Optional[int] = Field(default=None, primary_key=True)
    student_no: str = Field(max_length=64, unique=True, index=True, description="学号")
    name: str = Field(max_length=64, index=True, description="姓名")
    gender: Optional[str] = Field(default=None, max_length=8, description="性别")

    grade: int = Field(description="年级（7/8/9）")
    enrollment_year: Optional[int] = Field(default=None, description="入学年份")

    phone: Optional[str] = Field(default=None, max_length=20, description="联系电话")
    parent_phone: Optional[str] = Field(default=None, max_length=20, description="家长电话")

    # 学情统计缓存（避免每次重新计算）
    total_homework_count: int = Field(default=0, description="已参加作业数")
    average_score: Optional[float] = Field(default=None, description="平均分")

    notes: Optional[str] = Field(default=None, description="备注")
    is_active: bool = Field(default=True, description="是否在校")

    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    graduated_at: Optional[date] = Field(default=None, description="毕业日期")
