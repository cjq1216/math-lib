"""学生 API schema。"""

from datetime import date, datetime

from pydantic import Field

from app.schemas.common import StrictSchema


class StudentCreate(StrictSchema):
    student_no: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    gender: str | None = Field(default=None, max_length=8)
    grade: int = Field(ge=7, le=9)
    enrollment_year: int | None = Field(default=None, ge=2000, le=2100)
    phone: str | None = Field(default=None, max_length=20)
    parent_phone: str | None = Field(default=None, max_length=20)
    notes: str | None = None
    class_id: int | None = None


class StudentUpdate(StrictSchema):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    gender: str | None = Field(default=None, max_length=8)
    grade: int | None = Field(default=None, ge=7, le=9)
    enrollment_year: int | None = Field(default=None, ge=2000, le=2100)
    phone: str | None = Field(default=None, max_length=20)
    parent_phone: str | None = Field(default=None, max_length=20)
    notes: str | None = None
    graduated_at: date | None = None
    is_active: bool | None = None


class StudentRead(StrictSchema):
    id: int
    student_no: str
    name: str
    gender: str | None = None
    grade: int
    enrollment_year: int | None = None
    phone: str | None = None
    parent_phone: str | None = None
    average_score: float | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime
