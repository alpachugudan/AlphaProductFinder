from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.models import ReadyHealthResponse
from app.api.readiness import ReadinessService, get_readiness_service
from app.config.settings import Settings, get_settings

router = APIRouter(tags=["health"])


class LiveHealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


def get_active_settings(request: Request) -> Settings:
    """앱 팩터리 주입 설정 우선, 없으면 전역 Settings"""
    app_settings = getattr(request.app.state, "settings", None)
    if isinstance(app_settings, Settings):
        return app_settings
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_active_settings)]
ReadinessDep = Annotated[ReadinessService, Depends(get_readiness_service)]


@router.get("/health/live", response_model=LiveHealthResponse)
def live_health(settings: SettingsDep) -> LiveHealthResponse:
    """프로세스 생존 확인 — 외부 의존성 조회 없음"""
    return LiveHealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get("/health/ready", response_model=ReadyHealthResponse)
async def ready_health(
    readiness: ReadinessDep,
) -> JSONResponse:
    """DB·migration·active dataset·ontology·provider의 최근 검증 상태."""

    snapshot = await readiness.check()
    response = ReadyHealthResponse(
        status="ok" if snapshot.ready else "not_ready",
        checked_at=snapshot.checked_at,
        components=snapshot.components,
    )
    return JSONResponse(
        status_code=200 if snapshot.ready else 503,
        content=response.model_dump(mode="json"),
    )
