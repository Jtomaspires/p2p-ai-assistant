"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from settings import Settings


@pytest.fixture
def settings() -> Settings:
    """Return isolated settings with safe test defaults."""
    return Settings(
        _env_file=None,
        DATABASE_URL="sqlite://",
        REDIS_URL="redis://localhost:6379/15",
        NYLAS_SEND_ENABLED=False,
        SPF_DKIM_ENABLED=False,
        SECURITY_CHECK_ENABLED=False,
    )


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Provide an in-memory SQLite session for unit tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    SQLModel.metadata.drop_all(engine)
    engine.dispose()
