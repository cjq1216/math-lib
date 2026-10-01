"""媒体 API schema。"""

from datetime import datetime

from pydantic import Field

from app.models.media import MediaUsageType
from app.schemas.common import StrictSchema


class MediaUploadResponse(StrictSchema):
    id: int
    uuid: str
    url: str | None = None
    deduplicated: bool
    file_size: int = 0
    mime_type: str = "image/png"
    width: int | None = None
    height: int | None = None
    reference_count: int = 0


class MediaRead(StrictSchema):
    id: int
    uuid: str
    original_name: str
    url: str | None = None
    width: int | None = None
    height: int | None = None
    file_size: int
    mime_type: str | None = None
    reference_count: int = 0
    created_at: datetime | None = None


class QuestionMediaAssociatePayload(StrictSchema):
    media_id: int = Field(gt=0)
    usage_type: MediaUsageType = MediaUsageType.STEM
    display_order: int = Field(default=0, ge=0)
    alt_text: str | None = Field(default=None, max_length=255)
    caption: str | None = Field(default=None, max_length=64)
