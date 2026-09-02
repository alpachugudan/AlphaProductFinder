from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.answer import router as answer_router
from app.api.error_handlers import register_error_handlers
from app.api.health import router as health_router
from app.api.readiness import ReadinessService
from app.config.logging import bind_correlation_id, configure_logging, reset_correlation_id
from app.config.settings import Settings, get_settings


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """요청별 correlation ID 수신·생성 — Step 08 감사 로그 확장 훅"""

    header_name = "X-Correlation-ID"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get(self.header_name)
        correlation_id = incoming or str(uuid.uuid4())
        token = bind_correlation_id(correlation_id)
        try:
            response = await call_next(request)
        finally:
            reset_correlation_id(token)
        response.headers[self.header_name] = correlation_id
        return response


def create_app(settings_factory: Callable[[], Settings] | None = None) -> FastAPI:
    """FastAPI 애플리케이션 팩터리"""
    settings = (settings_factory or get_settings)()

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        try:
            if settings.app_env == "evaluation":
                await application.state.readiness_service.warmup_provider()
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.session_factory = session_factory
    application.state.readiness_service = ReadinessService(
        settings=settings,
        session_factory=session_factory,
    )
    application.add_middleware(CorrelationIdMiddleware)
    application.include_router(health_router)
    application.include_router(answer_router)
    register_error_handlers(application)

    return application


app = create_app()
