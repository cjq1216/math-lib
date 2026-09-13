"""
数据库连接、迁移与请求级会话。

MVP 使用同步 SQLModel Session。SQLite 目标负载较低，同步会话可以避免
在路由、服务和后台任务之间混用同步/异步 ORM API。
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine

from app.core.config import settings


def _make_engine() -> Engine:
    """根据配置创建同步引擎。"""
    url = settings.sync_database_url
    connect_args: dict[str, object] = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 5

    db_engine = create_engine(
        url,
        echo=settings.db_echo,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if url.startswith("sqlite"):

        @event.listens_for(db_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()

    return db_engine


engine = _make_engine()
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
)


def init_db() -> None:
    """开发环境启动时将数据库迁移到最新版本。"""
    if settings.app_env != "development":
        return

    from alembic.config import Config

    from alembic import command

    backend_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.sync_database_url)
    command.upgrade(cfg, "head")


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个同步 Session。"""
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
