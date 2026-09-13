"""班级与成员 API schema。"""

from pydantic import Field

from app.schemas.common import StrictSchema


class ClassCreate(StrictSchema):
    name: str = Field(min_length=1, max_length=64)
    grade: int = Field(ge=7, le=9)
    semester: str = Field(min_length=1, max_length=16)
    head_teacher_id: int | None = None
    teacher_ids: list[int] = Field(default_factory=list)
    notes: str | None = None


class ClassUpdate(StrictSchema):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    grade: int | None = Field(default=None, ge=7, le=9)
    semester: str | None = Field(default=None, min_length=1, max_length=16)
    head_teacher_id: int | None = None
    notes: str | None = None
    is_active: bool | None = None


class ClassRead(StrictSchema):
    id: int
    name: str
    grade: int
    semester: str
    head_teacher_id: int | None = None
    notes: str | None = None
    is_active: bool = True


class ClassTeacherSet(StrictSchema):
    teacher_ids: list[int] = Field(default_factory=list)


class ClassTeacherRead(StrictSchema):
    id: int
    username: str
    real_name: str


class ClassStudentRead(StrictSchema):
    student_id: int
    student_no: str
    name: str
    gender: str | None = None
    phone: str | None = None
