"""Backend test fixtures。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import models as _models  # noqa: F401
from app.core.database import get_session
from app.main import app


@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def client(test_engine):
    def override_get_session():
        with Session(test_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
