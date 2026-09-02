from __future__ import annotations

from app.config.settings import Settings, get_settings
from app.llm.base import LlmProvider
from app.llm.errors import HcxConfigurationError
from app.llm.hyperclova_provider import HyperClovaProvider
from app.llm.mock_provider import MockLlmProvider


def get_llm_provider(settings: Settings | None = None) -> LlmProvider:
    selected = settings or get_settings()
    if selected.llm_provider == "mock":
        return MockLlmProvider()
    if selected.hcx_api_key is None or not selected.hcx_api_key.get_secret_value().strip():
        raise HcxConfigurationError("HCX_API_KEY is required for LLM_PROVIDER=hyperclova")
    return HyperClovaProvider(selected)
