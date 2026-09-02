from __future__ import annotations

from app.core.errors import ConfigurationError, SystemUnavailableError


class HcxConfigurationError(ConfigurationError):
    """HCX provider configuration is absent or violates the billing policy."""


class HcxAuthenticationError(SystemUnavailableError):
    def __init__(self) -> None:
        super().__init__(code="HCX_AUTHENTICATION_FAILED", message="HCX authentication failed")


class HcxRateLimitError(SystemUnavailableError):
    def __init__(self) -> None:
        super().__init__(code="HCX_RATE_LIMITED", message="HCX rate limit reached")


class HcxTimeoutError(SystemUnavailableError):
    def __init__(self) -> None:
        super().__init__(code="HCX_TIMEOUT", message="HCX request timed out")


class HcxUnavailableError(SystemUnavailableError):
    def __init__(self) -> None:
        super().__init__(code="HCX_UNAVAILABLE", message="HCX service unavailable")


class HcxResponseError(SystemUnavailableError):
    def __init__(self) -> None:
        super().__init__(code="HCX_RESPONSE_INVALID", message="HCX response contract invalid")


class HcxAnswerIntegrityError(SystemUnavailableError):
    def __init__(self) -> None:
        super().__init__(
            code="HCX_ANSWER_INTEGRITY_FAILED",
            message="HCX answer failed safety checks",
        )
