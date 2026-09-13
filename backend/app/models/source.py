"""
题目来源表（Word/PDF 原始试卷）
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class SourceType(str, Enum):
    """来源类型"""

    MANUAL = "manual"           # 手工录入
    DOCX = "docx"               # Word 导入
    PDF = "pdf"                 # PDF 导入
    IMAGE = "image"             # 图片导入
    OCR = "ocr"                 # OCR 识别
    AI_GENERATED = "ai_generated"  # AI 生成


class Source(SQLModel, table=True):
    """题目来源文件"""

    __tablename__ = "sources"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(max_length=255, description="来源标题")
    source_type: SourceType = Field(default=SourceType.MANUAL)

    # 文件信息
    file_path: Optional[str] = Field(default=None, max_length=512)
    file_size: Optional[int] = Field(default=None)
    mime_type: Optional[str] = Field(default=None, max_length=64)

    # 试卷元数据
    publisher: Optional[str] = Field(default=None, max_length=128, description="出版社/出题人")
    publish_year: Optional[int] = Field(default=None)
    grade: Optional[int] = Field(default=None)
    region: Optional[str] = Field(default=None, max_length=64)

    # 解析状态
    parse_status: str = Field(default="pending", max_length=32, description="pending/processing/done/failed")
    parse_log: Optional[str] = Field(default=None)
    parsed_at: Optional[datetime] = Field(default=None)

    # 统计
    total_questions: int = Field(default=0, description="解析出的题目数")
    accepted_questions: int = Field(default=0, description="已入库题目数")

    notes: Optional[str] = Field(default=None)
    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
