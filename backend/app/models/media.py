"""
媒体资源表 - 统一管理所有图片/公式/附件

实现：
- MD5 去重（相同图只存一份）
- N:M 关联（一图多用）
- 分类存储（按用途分子目录）
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import JSON, Field, SQLModel


class MediaUsageType(str, Enum):
    """媒体用途"""

    STEM = "stem"              # 题干配图
    OPTION = "option"          # 选项图
    ANALYSIS = "analysis"      # 解析图
    ATTACHMENT = "attachment"  # 附件


class MediaResource(SQLModel, table=True):
    """媒体资源统一表"""

    __tablename__ = "media_resource"

    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(max_length=36, unique=True, index=True)

    original_name: str = Field(max_length=255)
    storage_path: str = Field(max_length=512)
    access_url: Optional[str] = Field(max_length=512)

    file_size: int = Field(description="字节")
    mime_type: str = Field(max_length=50)

    # 去重
    md5_hash: Optional[str] = Field(default=None, max_length=32, index=True)

    # 尺寸
    width: Optional[int] = Field(default=None)
    height: Optional[int] = Field(default=None)

    # 来源
    source: str = Field(default="upload", max_length=50, description="upload/ocr/generated")

    # 元数据
    alt_text: Optional[str] = Field(default=None, max_length=255)
    tags: Optional[list[str]] = Field(default=None, sa_type=JSON, description="等腰三角形/坐标系...")

    # 引用统计
    reference_count: int = Field(default=0, description="被多少题目引用")

    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QuestionMedia(SQLModel, table=True):
    """题目-媒体关联表（N:M）"""

    __tablename__ = "question_media"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: int = Field(foreign_key="questions.id", index=True, ondelete="CASCADE")
    media_id: int = Field(foreign_key="media_resource.id", index=True, ondelete="CASCADE")

    usage_type: MediaUsageType = Field(default=MediaUsageType.STEM)
    display_order: int = Field(default=0)

    alt_text: Optional[str] = Field(default=None, max_length=255)
    caption: Optional[str] = Field(default=None, max_length=64, description="图1/图2")

    created_at: datetime = Field(default_factory=datetime.utcnow)
