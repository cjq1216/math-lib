"""媒体资源上传、查询与删除。

功能：
1. MIME、扩展名、大小（10MB）白名单校验；
2. 真实图片格式与尺寸校验（Pillow 图像解码验证 / SVG XML 结构验证）；
3. MD5 内容去重（相同图片物理只存一份）；
4. 上传时初始引用计数为 0（仅当真正关联题目时增加）；
5. 异常回滚与孤儿文件自动清理；
6. 媒体相对/绝对 URL 动态生成；
7. 引用保护式删除（仅当真实无题目引用时允许物理删除）。
"""

import hashlib
import io
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlmodel import Session, func, select

from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.media import MediaResource, MediaUsageType, QuestionMedia
from app.models.user import User
from app.schemas.common import OkResponse
from app.schemas.media import MediaRead, MediaUploadResponse
from app.services.audit_service import add_audit_event

router = APIRouter()

MAX_MEDIA_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/svg+xml",
}


def build_media_url(storage_path: str) -> str:
    """生成媒体资源的访问地址。

    默认返回以 /static/ 开头的相对地址，在 Next.js 同源代理与多种生产部署下均能正确访问，
    杜绝将后端 localhost 硬编码写入数据库或返回给客户端。
    """
    configured_base = (settings.media_base_url or "").rstrip("/")
    if configured_base and "localhost" not in configured_base and configured_base != "http://localhost:8000/static":
        return f"{configured_base}/{storage_path}"
    return f"/static/{storage_path}"


def _validate_and_inspect_image(
    content: bytes, extension: str, content_type: str | None
) -> tuple[int | None, int | None, str]:
    """校验真实图片格式并提取尺寸与标准化 MIME。"""
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="文件内容不能为空")
    if len(content) > MAX_MEDIA_FILE_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"文件大小超过限制（当前 {len(content) / 1024 / 1024:.2f}MB，最大 10MB）",
        )

    ext = extension.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"不支持的文件扩展名 '{extension}'，仅支持 {sorted(ALLOWED_EXTENSIONS)}",
        )

    mime = (content_type or "").lower()
    if mime and mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"不支持的媒体 MIME 类型 '{content_type}'",
        )

    # 1. SVG 文件验证
    if ext == ".svg" or mime == "image/svg+xml":
        try:
            root = ET.fromstring(content)
            tag = root.tag.lower()
            if not tag.endswith("svg"):
                raise HTTPException(status_code=422, detail="无效的 SVG 矢量图结构")
            width_attr = root.attrib.get("width")
            height_attr = root.attrib.get("height")
            w = int(float(width_attr)) if width_attr and width_attr.replace(".", "", 1).isdigit() else None
            h = int(float(height_attr)) if height_attr and height_attr.replace(".", "", 1).isdigit() else None
            return w, h, "image/svg+xml"
        except ET.ParseError as e:
            raise HTTPException(status_code=422, detail=f"SVG 文件解析失败: {e}") from None

    # 2. 点阵图解码与有效性验证
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
            fmt = (img.format or "").upper()
            if fmt not in {"JPEG", "PNG", "WEBP", "GIF"}:
                raise HTTPException(status_code=422, detail=f"不支持的图片格式 '{fmt}'")

        # 重新 open 获取尺寸（verify 之后需要新实例才能获取尺寸）
        with Image.open(io.BytesIO(content)) as img:
            width, height = img.size
            final_mime = Image.MIME.get(img.format, mime or "image/png")
            return width, height, final_mime
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(status_code=422, detail=f"无效或已损坏的图片文件: {e}") from None


@router.post("/upload", response_model=MediaUploadResponse)
async def upload_media(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
    usage: MediaUsageType = MediaUsageType.STEM,
) -> MediaUploadResponse:
    """上传图片，执行安全校验、真实解码、孤儿文件清理与 MD5 去重。"""
    content = await file.read()
    extension = Path(file.filename or "image.png").suffix

    # 1. 深度安全校验与尺寸提取
    width, height, resolved_mime = _validate_and_inspect_image(
        content=content,
        extension=extension,
        content_type=file.content_type,
    )

    # 2. 计算 MD5
    md5 = hashlib.md5(content).hexdigest()

    # 3. MD5 查重（若已存在，返回现有记录，不在此步伪造增加引用计数）
    existing = session.exec(
        select(MediaResource).where(MediaResource.md5_hash == md5)
    ).first()
    if existing:
        add_audit_event(
            session,
            action="upload_deduplicated",
            resource_type="media",
            actor=current_user,
            resource_id=existing.id,
            changes={"md5": md5},
            request=request,
        )
        session.commit()
        return MediaUploadResponse(
            id=existing.id,
            uuid=existing.uuid,
            url=existing.access_url,
            deduplicated=True,
            file_size=existing.file_size,
            mime_type=existing.mime_type,
            width=existing.width,
            height=existing.height,
            reference_count=existing.reference_count,
        )

    # 4. 分配物理存储路径
    media_uuid = str(uuid.uuid4())
    sub_directory = {
        MediaUsageType.STEM: "question_images",
        MediaUsageType.OPTION: "option_images",
        MediaUsageType.ANALYSIS: "analysis_images",
        MediaUsageType.ATTACHMENT: "formula_images",
    }[usage]
    storage_path = f"{sub_directory}/{media_uuid}{extension}"
    full_path = Path(settings.media_root) / storage_path

    # 5. 写入磁盘并执行事务持久化；失败时清理孤儿物理文件
    written_to_disk = False
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        written_to_disk = True

        access_url = build_media_url(storage_path)

        media = MediaResource(
            uuid=media_uuid,
            original_name=file.filename or "unnamed",
            storage_path=storage_path,
            access_url=access_url,
            file_size=len(content),
            mime_type=resolved_mime,
            md5_hash=md5,
            width=width,
            height=height,
            source="upload",
            reference_count=0,  # 初始上传未被任何题目关联，引用计数严格为 0
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
            changes={
                "file_size": media.file_size,
                "mime_type": media.mime_type,
                "md5": md5,
            },
            request=request,
        )
        session.commit()

        return MediaUploadResponse(
            id=media.id,
            uuid=media.uuid,
            url=media.access_url,
            deduplicated=False,
            file_size=media.file_size,
            mime_type=media.mime_type,
            width=media.width,
            height=media.height,
            reference_count=media.reference_count,
        )
    except Exception:
        if written_to_disk:
            full_path.unlink(missing_ok=True)
        session.rollback()
        raise


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
            "mime_type": item.mime_type,
            "reference_count": item.reference_count,
            "created_at": item.created_at,
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
    """仅允许删除真实引用计数为 0 的媒体。"""
    media = session.get(MediaResource, media_id)
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="媒体不存在")

    # 双重校验真实关联数
    actual_refs = session.exec(
        select(func.count(QuestionMedia.id)).where(QuestionMedia.media_id == media_id)
    ).one()

    if actual_refs > 0 or media.reference_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该媒体仍被题目引用（引用数: {max(actual_refs, media.reference_count)}），不能删除",
        )

    # 删除物理文件
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
