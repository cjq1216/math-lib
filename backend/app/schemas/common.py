"""跨领域通用 API schema。"""

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrmSchema(StrictSchema):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class IdResponse(BaseModel):
    id: int


class OkResponse(BaseModel):
    ok: bool = True


class CountResponse(BaseModel):
    count: int = Field(ge=0)


class ImportErrorItem(BaseModel):
    row: int | None = None
    column: str | None = None
    code: str
    message: str


class ImportSummary(BaseModel):
    created: int = Field(default=0, ge=0)
    updated: int = Field(default=0, ge=0)
    errors: list[ImportErrorItem] = Field(default_factory=list)
