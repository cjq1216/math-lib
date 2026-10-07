"""系统运维与备份管理 API 路由。

仅限管理员 (admin) 访问。
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import require_admin
from app.models.user import User
from app.schemas.common import OkResponse
from app.schemas.system import (
    BackupCreateRequest,
    BackupItem,
    RestoreRequest,
    RestoreResponse,
)
from app.services.audit_service import add_audit_event
from app.services.backup_service import (
    create_backup,
    delete_backup_file,
    get_safe_backup_path,
    list_backups,
    restore_from_backup,
)

router = APIRouter()


@router.post(
    "/backup",
    response_model=BackupItem,
    summary="创建系统数据与媒体备份",
    status_code=status.HTTP_201_CREATED,
)
def api_create_backup(
    request: Request,
    payload: BackupCreateRequest | None = None,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> BackupItem:
    """创建包含数据库热快照与媒体资源的新备份。"""
    desc = payload.description if payload else None
    try:
        backup_item = create_backup(description=desc)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建备份失败: {err}",
        ) from err

    add_audit_event(
        session,
        action="create_backup",
        resource_type="system_backup",
        actor=current_user,
        changes={
            "filename": backup_item.filename,
            "backup_id": backup_item.backup_id,
            "size_bytes": backup_item.size_bytes,
            "description": desc,
        },
        request=request,
    )
    session.commit()
    return backup_item


@router.get(
    "/backups",
    response_model=list[BackupItem],
    summary="获取历史备份列表",
)
def api_list_backups(
    current_user: User = Depends(require_admin),
) -> list[BackupItem]:
    """返回所有历史有效及格式异常的备份文件列表。"""
    return list_backups()


@router.post(
    "/restore",
    response_model=RestoreResponse,
    summary="从备份文件执行系统恢复",
)
def api_restore_backup(
    request: Request,
    payload: RestoreRequest,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> RestoreResponse:
    """从指定的备份 ZIP 包恢复数据库和媒体文件。需传入 confirm=True 确认。"""
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须确认 confirm=True 方可执行覆盖恢复",
        )

    try:
        result = restore_from_backup(payload.filename)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"备份包检验失败: {err}",
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"恢复执行异常: {err}",
        ) from err

    add_audit_event(
        session,
        action="restore_backup",
        resource_type="system_backup",
        actor=current_user,
        changes={
            "filename": payload.filename,
            "pre_restore_backup": result.pre_restore_backup,
            "restored_media_count": result.media_file_count,
        },
        request=request,
    )
    session.commit()
    return result


@router.delete(
    "/backups/{filename}",
    response_model=OkResponse,
    summary="删除指定备份文件",
)
def api_delete_backup(
    filename: str,
    request: Request,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> OkResponse:
    """安全删除指定名称的备份归档包。"""
    try:
        delete_backup_file(filename)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    add_audit_event(
        session,
        action="delete_backup",
        resource_type="system_backup",
        actor=current_user,
        changes={"filename": filename},
        request=request,
    )
    session.commit()
    return OkResponse()


@router.get(
    "/backups/{filename}/download",
    summary="下载备份 ZIP 归档包",
)
def api_download_backup(
    filename: str,
    current_user: User = Depends(require_admin),
) -> FileResponse:
    """下载指定的备份文件。"""
    try:
        file_path = get_safe_backup_path(filename)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/zip",
    )
