from __future__ import annotations


class ProductFinderError(Exception):
    """도메인 공통 예외 베이스 — Step 09에서 HTTP 매핑 확장"""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ConfigurationError(ProductFinderError):
    """설정 검증 실패"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR")


class RetrieverFailure(ProductFinderError):
    """필수 Retriever 장애 — domain ABSTAIN과 구분되는 시스템 오류"""

    def __init__(self, retriever: str, message: str) -> None:
        super().__init__(message, code="RETRIEVER_FAILURE")
        self.retriever = retriever


class SystemUnavailableError(ProductFinderError):
    """재시도 가능한 인프라·무결성 장애."""

    def __init__(
        self,
        code: str = "SYSTEM_UNAVAILABLE",
        message: str = "service unavailable",
    ) -> None:
        super().__init__(message, code=code)


class RequestDeadlineExceeded(SystemUnavailableError):
    def __init__(self) -> None:
        super().__init__(code="REQUEST_DEADLINE_EXCEEDED", message="request deadline exceeded")
