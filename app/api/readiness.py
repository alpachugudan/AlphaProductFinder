from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import cast

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.settings import PROJECT_ROOT, Settings
from app.data.raw_models import DatasetVersion, DatasetVersionStatus
from app.llm.base import LlmProvider
from app.llm.factory import get_llm_provider
from app.query.registry import get_field_registry


@dataclass(frozen=True, slots=True)
class ReadinessSnapshot:
    ready: bool
    checked_at: str
    components: dict[str, str]


class ReadinessService:
    """의존성 상태를 짧게 cache해 readiness probe가 생성 호출을 반복하지 않게 한다."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: Callable[[], Session],
        provider_factory: Callable[[], LlmProvider] | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._provider_factory = provider_factory or (lambda: get_llm_provider(self._settings))
        self._snapshot: ReadinessSnapshot | None = None
        self._checked_monotonic = 0.0
        self._lock = asyncio.Lock()

    async def check(self) -> ReadinessSnapshot:
        if self._is_fresh():
            return cast(ReadinessSnapshot, self._snapshot)
        async with self._lock:
            if self._is_fresh():
                return cast(ReadinessSnapshot, self._snapshot)
            self._snapshot = await self._refresh()
            self._checked_monotonic = monotonic()
            return self._snapshot

    async def warmup_provider(self) -> None:
        """평가 환경 기동 시 1회만 capability smoke. readiness 요청 경로에서는 호출하지 않는다."""
        provider = self._provider_factory()
        smoke = getattr(provider, "capability_smoke", None)
        if smoke is not None:
            await smoke()
        health = await provider.healthcheck()
        if not isinstance(health, dict) or health.get("status") != "ok":
            msg = "LLM provider is not ready"
            raise RuntimeError(msg)

    def _is_fresh(self) -> bool:
        return (
            self._snapshot is not None
            and monotonic() - self._checked_monotonic < self._settings.readiness_cache_seconds
        )

    async def _refresh(self) -> ReadinessSnapshot:
        components = {
            "database": self._check_database(),
            "migration": self._check_migration(),
            "dataset": self._check_active_dataset(),
            "ontology_registry": self._check_ontology_registry(),
            "llm_provider": await self._check_provider(),
        }
        return ReadinessSnapshot(
            ready=all(value == "ok" for value in components.values()),
            checked_at=datetime.now(UTC).isoformat(),
            components=components,
        )

    def _check_database(self) -> str:
        try:
            session = self._session_factory()
            try:
                session.execute(text("SELECT 1"))
            finally:
                session.close()
        except SQLAlchemyError:
            return "unavailable"
        return "ok"

    def _check_migration(self) -> str:
        try:
            session = self._session_factory()
            try:
                current = session.scalar(text("SELECT version_num FROM alembic_version"))
            finally:
                session.close()
            config = Config(str(PROJECT_ROOT / "alembic.ini"))
            config.set_main_option("script_location", str(Path(PROJECT_ROOT / "alembic")))
            expected = ScriptDirectory.from_config(config).get_current_head()
        except (SQLAlchemyError, OSError):
            return "unavailable"
        return "ok" if current == expected else "outdated"

    def _check_active_dataset(self) -> str:
        try:
            session = self._session_factory()
            try:
                active = session.scalar(
                    select(DatasetVersion.id).where(
                        DatasetVersion.status == DatasetVersionStatus.ACTIVE.value
                    )
                )
            finally:
                session.close()
        except SQLAlchemyError:
            return "unavailable"
        return "ok" if active is not None else "unavailable"

    @staticmethod
    def _check_ontology_registry() -> str:
        try:
            return "ok" if get_field_registry().fields else "unavailable"
        except (OSError, ValueError, KeyError):
            return "unavailable"

    async def _check_provider(self) -> str:
        try:
            health = await self._provider_factory().healthcheck()
        except Exception:
            return "unavailable"
        if isinstance(health, dict) and health.get("status") == "ok":
            return "ok"
        return "unavailable"


def get_readiness_service(request: Request) -> ReadinessService:
    return cast(ReadinessService, request.app.state.readiness_service)
