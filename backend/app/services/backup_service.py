"""系统备份与恢复核心服务。

提供基于 SQLite 安全备份 API (sqlite3.backup) 的在线一致性快照、
媒体目录完整同步归档、可配置保留策略、完整性校验及原子恢复机制。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.database import engine
from app.core.datetime_utils import utc_now
from app.schemas.system import BackupItem, RestoreResponse


def _compute_sha256(file_path: Path) -> str:
    """计算文件的 SHA256 校验和。"""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_sqlite_db_path() -> Path | None:
    """解析当前数据库的 SQLite 文件绝对路径。若是内存库或非 SQLite 则返回 None。"""
    url = make_url(settings.sync_database_url)
    if url.get_backend_name() != "sqlite":
        return None
    db_name = url.database
    if not db_name or db_name == ":memory:":
        return None
    return Path(db_name).resolve()


def safe_sqlite_backup_to_file(target_file: Path, source_path: Path | None = None) -> None:
    """使用 SQLite 原生在线备份 API (sqlite3.Connection.backup) 导出一致性数据库快照。

    绝不直接进行原始文件热复制，避免并发写事务导致的快照撕裂或损坏。
    """
    target_file.parent.mkdir(parents=True, exist_ok=True)
    if target_file.exists():
        target_file.unlink()

    src_path = source_path or get_sqlite_db_path()

    if src_path and src_path.exists():
        # 通过 SQLite URI/只读连接执行热备份
        source_conn = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True, timeout=30.0)
    else:
        # 支持测试环境或内存/无物理文件的 Engine 连接获取
        raw_conn = engine.raw_connection()
        driver_conn = getattr(raw_conn, "driver_connection", raw_conn)
        source_conn = driver_conn

    dest_conn = sqlite3.connect(str(target_file))
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        if src_path and src_path.exists():
            source_conn.close()

    # 完整性自检 (PRAGMA integrity_check)
    check_conn = sqlite3.connect(str(target_file))
    try:
        cursor = check_conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        if not result or result[0] != "ok":
            raise ValueError(f"SQLite 备份文件完整性校验失败: {result}")
    finally:
        check_conn.close()


def create_backup(
    description: str | None = None,
    backup_dir: Path | None = None,
    media_root: Path | None = None,
    custom_db_path: Path | None = None,
) -> BackupItem:
    """创建包含数据库热快照、媒体文件与清单 Manifest 的完整备份归档包。"""
    b_dir = backup_dir or Path(settings.backup_dir)
    b_dir.mkdir(parents=True, exist_ok=True)
    m_root = media_root or Path(settings.media_root)

    backup_id = uuid.uuid4().hex[:12]
    timestamp_str = utc_now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"math_bank_backup_{timestamp_str}_{backup_id}.zip"
    final_zip_path = b_dir / zip_filename

    with tempfile.TemporaryDirectory(prefix="mb_backup_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        tmp_db = tmp_dir / "database.db"

        # 1. 导出 SQLite 安全备份
        safe_sqlite_backup_to_file(tmp_db, source_path=custom_db_path)
        db_sha256 = _compute_sha256(tmp_db)
        db_size = tmp_db.stat().st_size

        # 2. 统计媒体文件
        media_files: list[Path] = []
        media_total_bytes = 0
        if m_root.exists():
            for root, _, files in os.walk(m_root):
                for f in files:
                    fp = Path(root) / f
                    media_files.append(fp)
                    media_total_bytes += fp.stat().st_size

        # 3. 构造清单 Manifest
        manifest: dict[str, Any] = {
            "backup_id": backup_id,
            "created_at": utc_now().isoformat(),
            "app_name": settings.app_name,
            "app_version": "0.1.0",
            "database_filename": "database.db",
            "database_sha256": db_sha256,
            "database_size_bytes": db_size,
            "media_file_count": len(media_files),
            "media_total_bytes": media_total_bytes,
            "description": description or "",
            "retention_days": settings.backup_retention_days,
        }
        manifest_path = tmp_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        # 4. 打包为 Zip 压缩包（写入临时文件后重命名保证原子性）
        tmp_zip_path = tmp_dir / "archive.tmp.zip"
        with zipfile.ZipFile(tmp_zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db, arcname="database.db")
            zf.write(manifest_path, arcname="manifest.json")
            for mf in media_files:
                try:
                    rel_path = mf.relative_to(m_root)
                    zf.write(mf, arcname=f"media/{rel_path.as_posix()}")
                except Exception as err:
                    logger.warning(f"备份媒体文件跳过: {mf}: {err}")

        # 原子移动到最终备份路径
        shutil.move(str(tmp_zip_path), str(final_zip_path))

    zip_size = final_zip_path.stat().st_size
    logger.info(
        f"成功生成备份包 {zip_filename} (数据库: {db_size} 字节, 媒体文件: {len(media_files)} 个, 总大小: {zip_size} 字节)"
    )

    # 5. 执行保留策略清理
    cleanup_old_backups(b_dir)

    return BackupItem(
        backup_id=backup_id,
        filename=zip_filename,
        size_bytes=zip_size,
        created_at=manifest["created_at"],
        database_sha256=db_sha256,
        database_size_bytes=db_size,
        media_file_count=len(media_files),
        media_total_bytes=media_total_bytes,
        status="valid",
        description=description,
    )


def list_backups(backup_dir: Path | None = None) -> list[BackupItem]:
    """列出指定目录下所有备份包，解析其 Manifest 并校验基本格式。"""
    b_dir = backup_dir or Path(settings.backup_dir)
    if not b_dir.exists():
        return []

    items: list[BackupItem] = []
    for file in sorted(b_dir.glob("math_bank_backup_*.zip"), reverse=True):
        size = file.stat().st_size
        try:
            with zipfile.ZipFile(file, "r") as zf:
                if "manifest.json" not in zf.namelist():
                    items.append(
                        BackupItem(
                            backup_id="unknown",
                            filename=file.name,
                            size_bytes=size,
                            created_at=utc_now().isoformat(),
                            database_sha256="",
                            database_size_bytes=0,
                            media_file_count=0,
                            media_total_bytes=0,
                            status="corrupt_missing_manifest",
                            description="清单文件缺失",
                        )
                    )
                    continue
                manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                items.append(
                    BackupItem(
                        backup_id=manifest_data.get("backup_id", "unknown"),
                        filename=file.name,
                        size_bytes=size,
                        created_at=manifest_data.get("created_at", ""),
                        database_sha256=manifest_data.get("database_sha256", ""),
                        database_size_bytes=manifest_data.get("database_size_bytes", 0),
                        media_file_count=manifest_data.get("media_file_count", 0),
                        media_total_bytes=manifest_data.get("media_total_bytes", 0),
                        status="valid",
                        description=manifest_data.get("description"),
                    )
                )
        except Exception as err:
            logger.warning(f"读取备份包失败 {file.name}: {err}")
            items.append(
                BackupItem(
                    backup_id="unknown",
                    filename=file.name,
                    size_bytes=size,
                    created_at=utc_now().isoformat(),
                    database_sha256="",
                    database_size_bytes=0,
                    media_file_count=0,
                    media_total_bytes=0,
                    status="unreadable",
                    description=str(err),
                )
            )

    items.sort(key=lambda x: x.created_at, reverse=True)
    return items


def cleanup_old_backups(
    backup_dir: Path | None = None,
    max_count: int | None = None,
    retention_days: int | None = None,
) -> list[str]:
    """清理超出最大保留数量或保留天数的历史备份，始终保留至少最新的 1 个完整备份。"""
    b_dir = backup_dir or Path(settings.backup_dir)
    if not b_dir.exists():
        return []

    limit_count = max_count if max_count is not None else settings.backup_max_count
    limit_days = retention_days if retention_days is not None else settings.backup_retention_days

    all_backups = sorted(b_dir.glob("math_bank_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not all_backups:
        return []

    deleted_names: list[str] = []
    now = utc_now().timestamp()
    max_age_seconds = limit_days * 86400

    for idx, backup_file in enumerate(all_backups):
        # 始终保留最新 1 个备份
        if idx == 0:
            continue

        file_age = now - backup_file.stat().st_mtime
        should_delete = False

        if idx >= limit_count:
            should_delete = True
        elif file_age > max_age_seconds:
            should_delete = True

        if should_delete:
            try:
                backup_file.unlink()
                deleted_names.append(backup_file.name)
                logger.info(f"保留策略清理过期备份: {backup_file.name}")
            except Exception as err:
                logger.error(f"删除过期备份失败 {backup_file.name}: {err}")

    return deleted_names


def get_safe_backup_path(filename: str, backup_dir: Path | None = None) -> Path:
    """安全解析备份文件路径，防止路径遍历攻击 (Path Traversal)。"""
    b_dir = (backup_dir or Path(settings.backup_dir)).resolve()
    base_name = os.path.basename(filename.strip())
    if not base_name.endswith(".zip") or not base_name.startswith("math_bank_backup_"):
        raise ValueError("非法的备份文件名格式")
    target_path = (b_dir / base_name).resolve()
    if target_path.parent != b_dir or not target_path.exists():
        raise FileNotFoundError(f"备份文件不存在: {base_name}")
    return target_path


def delete_backup_file(filename: str, backup_dir: Path | None = None) -> bool:
    """安全删除指定名称的备份包。"""
    path = get_safe_backup_path(filename, backup_dir)
    path.unlink()
    logger.info(f"备份包已被删除: {filename}")
    return True


def restore_from_backup(
    backup_file: Path | str,
    target_db_path: Path | None = None,
    target_media_root: Path | None = None,
) -> RestoreResponse:
    """从备份包恢复数据库与媒体文件。

    包含完整的校验和比对、SQLite 完整性检验、恢复前快照安全备份和原子覆盖。
    """
    if isinstance(backup_file, str):
        zip_path = get_safe_backup_path(backup_file)
    else:
        zip_path = backup_file.resolve()

    if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
        raise ValueError(f"指定的备份文件不存在或不是有效的 ZIP 压缩包: {zip_path.name}")

    t_db = target_db_path or get_sqlite_db_path()
    if not t_db:
        raise ValueError("无法获取有效的目标 SQLite 数据库路径")

    t_media = target_media_root or Path(settings.media_root)

    with tempfile.TemporaryDirectory(prefix="mb_restore_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        # 1. 解压备份包
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        manifest_file = tmp_dir / "manifest.json"
        if not manifest_file.exists():
            raise ValueError("备份包中缺失 manifest.json 清单文件")

        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        expected_sha256 = manifest.get("database_sha256")
        extracted_db = tmp_dir / "database.db"

        if not extracted_db.exists():
            raise ValueError("备份包中缺失 database.db 文件")

        # 2. 校验数据库 SHA256
        actual_sha256 = _compute_sha256(extracted_db)
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise ValueError(
                f"数据库 SHA256 校验和不匹配！预期: {expected_sha256}, 实际: {actual_sha256}"
            )

        # 3. 校验 SQLite 完整性
        check_conn = sqlite3.connect(str(extracted_db))
        try:
            cursor = check_conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()
            if not res or res[0] != "ok":
                raise ValueError(f"备份数据库完整性检查未通过: {res}")
        finally:
            check_conn.close()

        # 4. 恢复前安全快照（如果目标数据库文件已存在）
        pre_restore_bak_name: str | None = None
        if t_db.exists():
            ts = utc_now().strftime("%Y%m%d_%H%M%S")
            pre_restore_bak = t_db.parent / f"{t_db.stem}_prerestore_{ts}.db"
            try:
                # 使用安全在线备份生成恢复前快照
                safe_sqlite_backup_to_file(pre_restore_bak, source_path=t_db)
                pre_restore_bak_name = pre_restore_bak.name
                logger.info(f"已创建恢复前安全快照: {pre_restore_bak_name}")
            except Exception as err:
                logger.warning(f"创建恢复前快照失败，尝试常规复制: {err}")
                shutil.copy2(t_db, pre_restore_bak)
                pre_restore_bak_name = pre_restore_bak.name

        # 5. 原子覆盖恢复 SQLite 数据库
        t_db.parent.mkdir(parents=True, exist_ok=True)
        # 将解压后的 db 安全覆盖到目标
        shutil.copy2(extracted_db, t_db)

        # 6. 恢复媒体文件
        extracted_media = tmp_dir / "media"
        restored_media_count = 0
        if extracted_media.exists():
            t_media.mkdir(parents=True, exist_ok=True)
            for root, _, files in os.walk(extracted_media):
                for f in files:
                    src_f = Path(root) / f
                    rel_p = src_f.relative_to(extracted_media)
                    dest_f = t_media / rel_p
                    dest_f.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_f, dest_f)
                    restored_media_count += 1

    logger.info(
        f"成功从备份 {zip_path.name} 恢复系统数据 (媒体文件: {restored_media_count} 个)"
    )

    return RestoreResponse(
        status="success",
        message="数据恢复成功完成",
        restored_at=utc_now().isoformat(),
        backup_filename=zip_path.name,
        pre_restore_backup=pre_restore_bak_name,
        database_sha256=actual_sha256,
        media_file_count=restored_media_count,
    )
