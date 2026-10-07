"""
FastAPI 应用入口
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import init_db
from app.middleware.request_logging import RequestLoggingMiddleware
from app.services.health_service import check_liveness, check_readiness


# 确保数据目录存在
def _ensure_data_dirs() -> None:
    """在应用构造前创建数据库、媒体、日志和导出目录。"""
    media_root = Path(settings.media_root)
    data_root = media_root.parent
    dirs = [
        data_root,
        media_root,
        media_root / "question_images",
        media_root / "option_images",
        media_root / "analysis_images",
        media_root / "formula_images",
        Path(settings.log_file).parent,
        data_root / "exports",
        Path(settings.backup_dir),
    ]
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)


# 配置日志
def _setup_logging() -> None:
    """配置 loguru 日志"""
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level=settings.log_level,
    )
    # 文件日志（仅生产环境）
    if settings.app_env == "production":
        logger.add(
            settings.log_file,
            rotation="100 MB",
            retention="30 days",
            level="INFO",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动 / 关闭"""
    _ensure_data_dirs()
    _setup_logging()
    logger.info(f"Starting {settings.app_name} in {settings.app_env} mode")

    # 初始化数据库
    init_db()
    logger.info("Database initialized")

    # 启动时扫描并自愈遗留 running 状态的孤儿后台任务
    from app.core.database import SessionLocal
    from app.services.task_service import recover_orphaned_tasks

    with SessionLocal() as db_session:
        recovered = recover_orphaned_tasks(db_session)
        if recovered > 0:
            logger.warning(f"服务启动自愈：已将 {recovered} 个遗留未完成后台任务标记为中断失败")
    yield

    logger.info("Shutting down")


# StaticFiles 会在应用构造时检查目录，必须先创建。
_ensure_data_dirs()


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description="初中数学题库与学情分析系统",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_debug else None,
    redoc_url="/redoc" if settings.app_debug else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)


# 静态文件（媒体）
app.mount(
    "/static",
    StaticFiles(directory=settings.media_root),
    name="static",
)

# 挂载 API 路由
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
async def health() -> dict[str, Any]:
    """综合健康检查（向后兼容）。"""
    is_ready, _ = check_readiness()
    return {
        "status": "ok" if is_ready else "degraded",
        "app": settings.app_name,
        "live": True,
        "ready": is_ready,
    }


@app.get("/health/live", tags=["health"])
async def health_live() -> dict[str, Any]:
    """存活探针 (Liveness Probe)：验证进程与事件循环处于正常响应状态。"""
    return check_liveness()


@app.get("/health/ready", tags=["health"])
async def health_ready(response: Response) -> dict[str, Any]:
    """就绪探针 (Readiness Probe)：验证数据库连通性及关键数据/媒体/日志/备份目录可写状态。"""
    is_ready, details = check_readiness()
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return details


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
