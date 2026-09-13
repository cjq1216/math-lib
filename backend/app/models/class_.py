"""
班级表 + 班级-学生关联
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Class(SQLModel, table=True):
    """班级表"""

    __tablename__ = "classes"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=64, index=True, description="班级名称")
    grade: int = Field(description="年级（7/8/9）")
    semester: str = Field(max_length=16, description="学期（如 2026-Spring）")

    # 班主任
    head_teacher_id: Optional[int] = Field(default=None, foreign_key="users.id")

    # 关联教师（多人带一个班）
    # 通过 class_teachers 关联表实现

    notes: Optional[str] = Field(default=None, description="备注")
    is_active: bool = Field(default=True)

    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ClassTeacher(SQLModel, table=True):
    """班级-教师关联；支持一个班级由多位教师共同维护。"""

    __tablename__ = "class_teachers"
    __table_args__ = (
        UniqueConstraint("class_id", "teacher_id", name="uq_class_teachers_class_teacher"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    class_id: int = Field(foreign_key="classes.id", index=True, ondelete="CASCADE")
    teacher_id: int = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    assigned_by: Optional[int] = Field(default=None, foreign_key="users.id")
    assigned_at: datetime = Field(default_factory=datetime.utcnow)


class ClassStudent(SQLModel, table=True):
    """班级-学生关联表"""

    __tablename__ = "class_students"

    id: Optional[int] = Field(default=None, primary_key=True)
    class_id: int = Field(foreign_key="classes.id", index=True)
    student_id: int = Field(foreign_key="students.id", index=True)
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    left_at: Optional[datetime] = Field(default=None)
    notes: Optional[str] = Field(default=None)
