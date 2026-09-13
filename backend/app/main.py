"""
FastAPI 应用入口
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import init_db


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

# 静态文件（媒体）
app.mount(
    "/static",
    StaticFiles(directory=settings.media_root),
    name="static",
)

# 挂载 API 路由
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """健康检查"""
    return {"status": "ok", "app": settings.app_name}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
