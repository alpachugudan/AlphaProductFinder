from __future__ import annotations

from pathlib import Path

import pytest
from app.config.settings import PROJECT_ROOT, Settings, get_settings
from pydantic import SecretStr, ValidationError


def test_settings_defaults() -> None:
    # 개발자의 .env(HCX key/provider)를 읽지 않고 코드 기본값만 검증한다.
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.app_name == "miraeasset-product-finder"
    assert settings.llm_provider == "mock"
    assert settings.default_result_limit == 5
    assert settings.max_result_limit == 10
    assert settings.internal_timeout_seconds == 120


def test_invalid_app_env_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production")  # type: ignore[arg-type]


def test_invalid_llm_provider_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(llm_provider="openai")  # type: ignore[arg-type]


def test_empty_app_name_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(app_name="   ")


def test_result_limit_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(default_result_limit=11)
    with pytest.raises(ValidationError):
        Settings(max_result_limit=9)


def test_timeout_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(internal_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(internal_timeout_seconds=300)


def test_source_data_dir_resolved_from_project_root() -> None:
    settings = Settings(source_data_dir=Path("../데이터셋"))
    resolved = settings.resolved_source_data_dir()
    assert resolved == (PROJECT_ROOT / "../데이터셋").resolve()


def test_environment_variable_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEFAULT_RESULT_LIMIT", "3")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.app_env == "test"
    assert settings.default_result_limit == 3


def test_database_url_not_in_safe_log_context() -> None:
    settings = Settings(database_url="postgresql+psycopg://secret:secret@localhost/db")
    safe_context = settings.safe_log_context()
    rendered = str(safe_context)
    assert "secret:secret" not in rendered
    assert "database_url" not in rendered


def test_evaluation_requires_hcx_key_and_credit_confirmation() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="evaluation",
            llm_provider="hyperclova",
            hcx_api_key=None,
            credit_balance_confirmed=True,
        )
    with pytest.raises(ValidationError):
        Settings(
            app_env="evaluation",
            llm_provider="hyperclova",
            hcx_api_key=SecretStr("test-key"),
            credit_balance_confirmed=False,
        )


def test_evaluation_accepts_confirmed_hcx_007_credit_only() -> None:
    settings = Settings(
        app_env="evaluation",
        llm_provider="hyperclova",
        hcx_api_key=SecretStr("test-key"),
        credit_balance_confirmed=True,
    )
    assert settings.hcx_intent_model == "HCX-007"
    assert "test-key" not in str(settings.safe_log_context())
