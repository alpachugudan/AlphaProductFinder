from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from app.config.settings import PROJECT_ROOT, get_settings
from app.db.session import get_engine
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", get_settings().database_url)


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    engine = create_engine(_database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def pgvector_available(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as connection:
        autocommit = connection.execution_options(isolation_level="AUTOCOMMIT")
        exists = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
        if exists is None:
            autocommit.execute(text("CREATE EXTENSION vector"))


@pytest.fixture
def alembic_config() -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return cfg


@pytest.fixture
def db_session(postgres_engine: Engine, alembic_config: Config) -> Generator[Session, None, None]:
    get_engine.cache_clear()
    get_settings.cache_clear()

    autocommit = postgres_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    autocommit.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    autocommit.execute(text("CREATE SCHEMA public"))
    autocommit.execute(text("GRANT ALL ON SCHEMA public TO public"))
    autocommit.close()

    command.upgrade(alembic_config, "head")

    session = sessionmaker(bind=postgres_engine, autoflush=False, autocommit=False)()
    yield session
    session.close()
