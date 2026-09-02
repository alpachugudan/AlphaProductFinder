from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.query.models import QuerySpec


@runtime_checkable
class LlmProvider(Protocol):
    async def parse_query(self, question: str) -> QuerySpec: ...

    async def generate_answer(self, context: object) -> str: ...

    async def regenerate_answer(self, context: object, guard_reasons: list[str]) -> str: ...

    async def healthcheck(self) -> object: ...
