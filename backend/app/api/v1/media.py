"""
媒体资源路由 - 图片上传/查询
"""

import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import get_session
from app.models.media import MediaResource

router = APIRouter()


@router.post("/upload")
async def upload_media(
    session: Annotated[Session, Depends(get_session)],
    file: UploadFile = File(...),
    usage: str = "stem",
):
    """
    上传图片（自动 MD5 去重）

    usage: stem / option / analysis / attachment
    """
    content = await file.read()
    md5 = hashlib.md5(content).hexdigest()

    # 查重
    existing = session.exec(select(MediaResource).where(MediaResource.md5_hash == md5)).first()

    if existing:
        # 增加引用计数
        existing.reference_count += 1
        session.add(existing)
        session.commit()
        return {
            "id": existing.id,
            "uuid": existing.uuid,
            "url": existing.access_url,
            "deduplicated": True,
        }

    # 存储
    media_uuid = str(uuid.uuid4())
    ext = Path(file.filename or "image.png").suffix
    sub_dir = {
        "stem": "question_images",
        "option": "option_images",
        "analysis": "analysis_images",
        "attachment": "formula_images",
    }.get(usage, "question_images")

    storage_path = f"{sub_dir}/{media_uuid}{ext}"
    full_path = Path(settings.media_root) / storage_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)

    # 获取尺寸（如可用）
    width = height = None
    try:
        from PIL import Image

        with Image.open(full_path) as img:
            width, height = img.size
    except ImportError:
        pass  # 没装 PIL 时跳过
    except Exception:
        pass

    media = MediaResource(
        uuid=media_uuid,
        original_name=file.filename or "unnamed",
        storage_path=storage_path,
        access_url=f"{settings.media_base_url}/{storage_path}",
        file_size=len(content),
        mime_type=file.content_type or "image/png",
        md5_hash=md5,
        width=width,
        height=height,
        source="upload",
        reference_count=1,
    )
    session.add(media)
    session.commit()
    session.refresh(media)

    return {
        "id": media.id,
        "uuid": media.uuid,
        "url": media.access_url,
        "deduplicated": False,
    }


@router.get("/")
def list_media(
    session: Annotated[Session, Depends(get_session)],
    skip: int = 0,
    limit: int = 50,
):
    """列出媒体资源"""
    items = session.exec(
        select(MediaResource).order_by(MediaResource.created_at.desc()).offset(skip).limit(limit)
    ).all()
    return [
        {
            "id": m.id,
            "uuid": m.uuid,
            "original_name": m.original_name,
            "url": m.access_url,
            "width": m.width,
            "height": m.height,
            "file_size": m.file_size,
            "reference_count": m.reference_count,
        }
        for m in items
    ]


@router.delete("/{media_id}")
def delete_media(
    media_id: int,
    session: Annotated[Session, Depends(get_session)],
):
    """删除媒体（仅当引用计数=0）"""
    media = session.get(MediaResource, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="媒体不存在")
    if media.reference_count > 0:
        raise HTTPException(status_code=400, detail="该媒体还被引用，不能删除")
    # 删除文件
    try:
        Path(settings.media_root) / media.storage_path
        (Path(settings.media_root) / media.storage_path).unlink(missing_ok=True)
    except Exception:
        pass
    session.delete(media)
    session.commit()
    return {"ok": True}
