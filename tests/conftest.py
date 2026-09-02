from __future__ import annotations

import asyncio
import sys
from collections.abc import Generator

import pytest
from app.config.settings import Settings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Windows Proactor self-pipe 오류를 피하고 CI와 동일한 selector loop로 고정한다."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost:5432/test_db",
    )


@pytest.fixture
def client(test_settings: Settings) -> Generator[TestClient, None, None]:
    application = create_app(lambda: test_settings)
    with TestClient(application) as test_client:
        yield test_client
