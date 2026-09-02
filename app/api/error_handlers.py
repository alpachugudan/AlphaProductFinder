from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.models import AnswerResponse
from app.core.errors import ProductFinderError

logger = logging.getLogger(__name__)


def system_failure_response(request: Request, *, code: str) -> JSONResponse:
    """시스템 장애도 외부 계약을 깨지 않고 재시도 가능하게 표시한다."""

    payload = AnswerResponse(
        question_id=request.query_params.get("question_id", ""),
        question=request.query_params.get("question", ""),
        retrieved_context="",
        think_trace=json.dumps(
            {"decision_state": "SYSTEM_ERROR", "error_code": code},
            sort_keys=True,
            separators=(",", ":"),
        ),
        answer="SYSTEM_ERROR: 일시적인 시스템 오류입니다. 잠시 후 다시 요청해 주세요.",
    )
    return JSONResponse(status_code=503, content=payload.model_dump())


def register_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(ProductFinderError)
    async def product_finder_error_handler(
        request: Request, exc: ProductFinderError
    ) -> JSONResponse:
        logger.exception("product finder request failed", extra={"error_code": exc.code})
        if request.url.path == "/answer":
            return system_failure_response(request, code=exc.code)
        return JSONResponse(
            status_code=500,
            content={"code": exc.code, "message": "internal error"},
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, _: Exception) -> JSONResponse:
        logger.exception("unexpected request failure")
        if request.url.path == "/answer":
            return system_failure_response(request, code="INTERNAL_ERROR")
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "internal error"},
        )
