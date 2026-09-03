from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "test", "evaluation"]
LlmProvider = Literal["mock", "hyperclova"]
BillingMode = Literal["credit_only", "allow_paid"]

# resource/ 디렉터리 — pyproject.toml과 동일 레벨
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """환경변수 기반 단일 설정 객체"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = "development"
    app_name: str = "miraeasset-product-finder"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/product_finder"
    source_data_dir: Path = Field(default=Path("../데이터셋"))
    llm_provider: LlmProvider = "mock"
    hcx_api_key: SecretStr | None = None
    hcx_base_url: str = "https://clovastudio.stream.ntruss.com"
    hcx_intent_model: str = "HCX-007"
    hcx_answer_model: str = "HCX-007"
    hcx_connect_timeout_seconds: float = 5.0
    hcx_read_timeout_seconds: float = 20.0
    hcx_max_retries: int = 1
    hcx_prompt_version: str = "hcx-v2"
    hcx_startup_smoke_enabled: bool = False
    billing_mode: BillingMode = "credit_only"
    credit_balance_confirmed: bool = False
    ncp_embedding_enabled: bool = False
    ncp_embedding_model: str = "bge-m3"
    internal_timeout_seconds: int = 120
    max_question_length: int = 4000
    cache_capacity: int = 128
    readiness_cache_seconds: int = 30
    default_result_limit: int = 5
    max_result_limit: int = 10

    @field_validator("app_name")
    @classmethod
    def app_name_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            msg = "APP_NAME must not be empty"
            raise ValueError(msg)
        return value

    @field_validator("log_level")
    @classmethod
    def log_level_must_be_valid(cls, value: str) -> str:
        normalized = value.upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in valid_levels:
            msg = f"LOG_LEVEL must be one of {sorted(valid_levels)}"
            raise ValueError(msg)
        return normalized

    @field_validator("hcx_base_url")
    @classmethod
    def hcx_base_url_must_be_https(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith("https://"):
            msg = "HCX_BASE_URL must use https"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def validate_limits_and_timeout(self) -> Settings:
        if self.max_result_limit != 10:
            msg = "MAX_RESULT_LIMIT must be fixed at 10"
            raise ValueError(msg)
        if not 1 <= self.default_result_limit <= self.max_result_limit:
            msg = "DEFAULT_RESULT_LIMIT must be between 1 and MAX_RESULT_LIMIT"
            raise ValueError(msg)
        if not 1 <= self.internal_timeout_seconds < 300:
            msg = "INTERNAL_TIMEOUT_SECONDS must be >= 1 and < 300"
            raise ValueError(msg)
        if not 1 <= self.max_question_length <= 20_000:
            msg = "MAX_QUESTION_LENGTH must be between 1 and 20000"
            raise ValueError(msg)
        if not 1 <= self.cache_capacity <= 10_000:
            msg = "CACHE_CAPACITY must be between 1 and 10000"
            raise ValueError(msg)
        if not 1 <= self.readiness_cache_seconds <= 300:
            msg = "READINESS_CACHE_SECONDS must be between 1 and 300"
            raise ValueError(msg)
        if self.llm_provider == "hyperclova":
            if not 0 < self.hcx_connect_timeout_seconds < self.internal_timeout_seconds:
                msg = (
                    "HCX_CONNECT_TIMEOUT_SECONDS must be positive and below "
                    "INTERNAL_TIMEOUT_SECONDS"
                )
                raise ValueError(msg)
            if not 0 < self.hcx_read_timeout_seconds < self.internal_timeout_seconds:
                msg = (
                    "HCX_READ_TIMEOUT_SECONDS must be positive and below "
                    "INTERNAL_TIMEOUT_SECONDS"
                )
                raise ValueError(msg)
        if not 0 <= self.hcx_max_retries <= 2:
            msg = "HCX_MAX_RETRIES must be between 0 and 2"
            raise ValueError(msg)
        if not self.hcx_prompt_version.strip():
            msg = "HCX_PROMPT_VERSION must not be empty"
            raise ValueError(msg)
        if self.app_env == "evaluation":
            if self.llm_provider != "hyperclova":
                msg = "APP_ENV=evaluation requires LLM_PROVIDER=hyperclova"
                raise ValueError(msg)
            if self.hcx_api_key is None or not self.hcx_api_key.get_secret_value().strip():
                msg = "APP_ENV=evaluation requires HCX_API_KEY"
                raise ValueError(msg)
            if self.hcx_intent_model != "HCX-007" or self.hcx_answer_model != "HCX-007":
                msg = "APP_ENV=evaluation permits HCX-007 only"
                raise ValueError(msg)
            if self.billing_mode == "credit_only" and not self.credit_balance_confirmed:
                msg = "APP_ENV=evaluation requires confirmed credit balance in credit_only mode"
                raise ValueError(msg)
        return self

    def resolved_source_data_dir(self) -> Path:
        """프로젝트 루트 기준으로 SOURCE_DATA_DIR 해석"""
        if self.source_data_dir.is_absolute():
            return self.source_data_dir
        return (PROJECT_ROOT / self.source_data_dir).resolve()

    def safe_log_context(self) -> dict[str, str]:
        """로그·오류 응답용 — DATABASE_URL 등 비밀 필드 제외"""
        return {
            "app_env": self.app_env,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "llm_provider": self.llm_provider,
            "billing_mode": self.billing_mode,
            "ncp_embedding_enabled": str(self.ncp_embedding_enabled).lower(),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
