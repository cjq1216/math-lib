"""媒体资源上传、查询与删除。"""

import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.media import MediaResource, MediaUsageType
from app.models.user import User
from app.schemas.common import OkResponse
from app.schemas.media import MediaRead, MediaUploadResponse
from app.services.audit_service import add_audit_event

router = APIRouter()


@router.post("/upload", response_model=MediaUploadResponse)
async def upload_media(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
    usage: MediaUsageType = MediaUsageType.STEM,
) -> MediaUploadResponse:
    """上传图片并按 MD5 去重。"""
    content = await file.read()
    md5 = hashlib.md5(content).hexdigest()
    existing = session.exec(
        select(MediaResource).where(MediaResource.md5_hash == md5)
    ).first()
    if existing:
        existing.reference_count += 1
        session.add(existing)
        add_audit_event(
            session,
            action="upload_deduplicated",
            resource_type="media",
            actor=current_user,
            resource_id=existing.id,
            request=request,
        )
        session.commit()
        return MediaUploadResponse(
            id=existing.id,
            uuid=existing.uuid,
            url=existing.access_url,
            deduplicated=True,
        )

    media_uuid = str(uuid.uuid4())
    extension = Path(file.filename or "image.png").suffix
    sub_directory = {
        MediaUsageType.STEM: "question_images",
        MediaUsageType.OPTION: "option_images",
        MediaUsageType.ANALYSIS: "analysis_images",
        MediaUsageType.ATTACHMENT: "formula_images",
    }[usage]
    storage_path = f"{sub_directory}/{media_uuid}{extension}"
    full_path = Path(settings.media_root) / storage_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)

    width = height = None
    try:
        from PIL import Image

        with Image.open(full_path) as image:
            width, height = image.size
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
        created_by=current_user.id,
    )
    session.add(media)
    session.flush()
    add_audit_event(
        session,
        action="upload",
        resource_type="media",
        actor=current_user,
        resource_id=media.id,
        changes={"file_size": media.file_size, "mime_type": media.mime_type},
        request=request,
    )
    session.commit()
    return MediaUploadResponse(
        id=media.id,
        uuid=media.uuid,
        url=media.access_url,
        deduplicated=False,
    )


@router.get("/", response_model=list[MediaRead])
def list_media(
    session: Annotated[Session, Depends(get_session)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> list[dict]:
    """列出机构共享媒体资源。"""
    items = session.exec(
        select(MediaResource)
        .order_by(MediaResource.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return [
        {
            "id": item.id,
            "uuid": item.uuid,
            "original_name": item.original_name,
            "url": item.access_url,
            "width": item.width,
            "height": item.height,
            "file_size": item.file_size,
            "reference_count": item.reference_count,
        }
        for item in items
    ]


@router.delete("/{media_id}", response_model=OkResponse)
def delete_media(
    media_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OkResponse:
    """仅删除没有引用的媒体。"""
    media = session.get(MediaResource, media_id)
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="媒体不存在")
    if media.reference_count > 0:
        raise HTTPException(status_code=400, detail="该媒体还被引用，不能删除")
    (Path(settings.media_root) / media.storage_path).unlink(missing_ok=True)
    session.delete(media)
    add_audit_event(
        session,
        action="delete",
        resource_type="media",
        actor=current_user,
        resource_id=media_id,
        request=request,
    )
    session.commit()
    return OkResponse()
