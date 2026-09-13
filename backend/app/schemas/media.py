"""媒体 API schema。"""

from app.schemas.common import StrictSchema


class MediaUploadResponse(StrictSchema):
    id: int
    uuid: str
    url: str | None = None
    deduplicated: bool


class MediaRead(StrictSchema):
    id: int
    uuid: str
    original_name: str
    url: str | None = None
    width: int | None = None
    height: int | None = None
    file_size: int
    reference_count: int
