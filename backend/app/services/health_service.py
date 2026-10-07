"""系统健康探针服务。

区分 Liveness (存活) 与 Readiness (就绪) 探针，检查数据库与各关键存储目录。
"""

import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.core.datetime_utils import utc_now


def _check_dir_writable(path: Path) -> tuple[bool, str]:
    """探测目录是否存在且具备可写权限。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / f".probe_{int(time.time() * 1000)}"
        test_file.write_text("probe", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return True, "writable"
    except Exception as err:
        return False, f"write test failed: {err}"


def check_liveness() -> dict[str, Any]:
    """存活检查：仅验证 HTTP 事件循环可正常响应。"""
    return {
        "status": "alive",
        "app": settings.app_name,
        "timestamp": utc_now().isoformat(),
    }


def check_readiness() -> tuple[bool, dict[str, Any]]:
    """就绪检查：综合验证数据库连通性与关键数据/媒体/日志/备份目录的可写状态。"""
    checks: dict[str, dict[str, Any]] = {}
    is_ready = True

    # 1. 探测数据库
    db_start = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_latency = round((time.perf_counter() - db_start) * 1000, 2)
        checks["database"] = {
            "healthy": True,
            "message": "connected",
            "latency_ms": db_latency,
        }
    except Exception as err:
        is_ready = False
        db_latency = round((time.perf_counter() - db_start) * 1000, 2)
        checks["database"] = {
            "healthy": False,
            "message": f"connection failed: {err}",
            "latency_ms": db_latency,
        }

    # 2. 探测存储目录可写性
    storage_targets = [
        ("storage_media", Path(settings.media_root)),
        ("storage_logs", Path(settings.log_file).parent),
        ("storage_exports", Path(settings.media_root).parent / "exports"),
        ("storage_backups", Path(settings.backup_dir)),
    ]

    for name, directory in storage_targets:
        healthy, message = _check_dir_writable(directory)
        checks[name] = {
            "healthy": healthy,
            "message": message,
            "path": str(directory),
        }
        if not healthy:
            is_ready = False

    payload = {
        "status": "ready" if is_ready else "unhealthy",
        "app": settings.app_name,
        "version": "0.1.0",
        "environment": settings.app_env,
        "timestamp": utc_now().isoformat(),
        "checks": checks,
    }

    return is_ready, payload
