"""R0 回归：空库迁移和最小 API 闭环。"""

from pathlib import Path

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from alembic import command
from app import models as _models  # noqa: F401
from app.core.database import get_session
from app.main import app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_migrations_upgrade_empty_database(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    migrated_engine = create_engine(database_url)
    try:
        tables = set(inspect(migrated_engine).get_table_names())
    finally:
        migrated_engine.dispose()

    assert {
        "alembic_version",
        "users",
        "questions",
        "question_embeddings",
        "papers",
        "homework",
        "background_tasks",
    } <= tables


def test_auth_migration_backfills_head_teacher(tmp_path: Path) -> None:
    database_path = tmp_path / "backfill.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "0003_background_tasks")

    migrated_engine = create_engine(database_url)
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, real_name, role, is_active) "
                "VALUES (1, 'teacher', 'hash', '教师', 'teacher', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO classes "
                "(id, name, grade, semester, head_teacher_id, is_active, created_by) "
                "VALUES (1, '测试班', 7, '2026-Fall', 1, 1, 1)"
            )
        )
    command.upgrade(config, "head")

    try:
        with migrated_engine.connect() as connection:
            relation = connection.execute(
                text(
                    "SELECT class_id, teacher_id, assigned_by FROM class_teachers "
                    "WHERE class_id = 1"
                )
            ).one()
            assert tuple(relation) == (1, 1, 1)
    finally:
        migrated_engine.dispose()


def test_register_login_and_question_crud_smoke() -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)

    def override_get_session():
        with Session(test_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    try:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "username": "admin",
                "password": "password123",
                "real_name": "管理员",
            },
        )
        assert register.status_code == 200, register.text
        assert register.json()["user"]["role"] == "admin"

        login = client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "password123"},
        )
        assert login.status_code == 200, login.text
        access_token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        created = client.post(
            "/api/v1/questions/",
            headers=headers,
            json={
                "stem": "已知 $x+1=2$，求 $x$。",
                "question_type": "solution",
                "difficulty": 1,
                "total_score": 5,
                "answer": "$x=1$",
            },
        )
        assert created.status_code == 201, created.text
        question_id = created.json()["id"]

        fetched = client.get(f"/api/v1/questions/{question_id}", headers=headers)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["stem"] == "已知 $x+1=2$，求 $x$。"
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()
