from __future__ import annotations

import json
from pathlib import Path

from app.agent.decision import DecisionState
from app.config.settings import PROJECT_ROOT
from app.evidence.models import AnswerContext
from app.query.models import QuerySpec
from app.query.registry import get_field_registry
from app.query.validator import validate_queryspec_or_raise

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "queryspec"
QUESTION_MAP_PATH = FIXTURE_DIR / "questions.json"
ANSWER_TEMPLATE_PATH = FIXTURE_DIR / "answer_templates.json"


class MockLlmError(Exception):
    pass


class MockLlmProvider:
    """fixture 질문만 결정적으로 QuerySpec·Answer 반환"""

    prompt_version = "mock-v1"

    def __init__(self, fixture_dir: Path = FIXTURE_DIR) -> None:
        self._fixture_dir = fixture_dir
        self._question_map: dict[str, str] = json.loads(
            QUESTION_MAP_PATH.read_text(encoding="utf-8")
        )
        if ANSWER_TEMPLATE_PATH.exists():
            self._answer_templates: dict[str, str] = json.loads(
                ANSWER_TEMPLATE_PATH.read_text(encoding="utf-8")
            )
        else:
            self._answer_templates = {}

    async def parse_query(self, question: str) -> QuerySpec:
        normalized = question.strip()
        fixture_name = self._question_map.get(normalized)
        if fixture_name is None:
            msg = f"unknown mock question: {normalized}"
            raise MockLlmError(msg)
        payload = json.loads((self._fixture_dir / fixture_name).read_text(encoding="utf-8"))
        spec = QuerySpec.model_validate(payload)
        validate_queryspec_or_raise(spec, get_field_registry())
        return spec

    async def generate_answer(self, context: object) -> str:
        if not isinstance(context, AnswerContext):
            msg = "generate_answer expects AnswerContext"
            raise TypeError(msg)

        state = context.decision.state
        if state == DecisionState.ASK:
            missing = "; ".join(context.decision.missing_requirements[:2]) or "추가 조건 필요"
            return (
                "ASK: 요청 조건이 명확하지 않아 임의 기준을 적용하지 않았습니다. "
                f"확인 필요: {missing}"
            )
        if state == DecisionState.ABSTAIN:
            reason_codes = context.decision.reason_codes
            code = reason_codes[0].value if reason_codes else "UNKNOWN"
            return (
                "ABSTAIN: 제공 데이터와 공식 근거만으로는 결론을 확인할 수 없습니다. "
                f"reason={code}"
            )
        if state in {DecisionState.ANSWER, DecisionState.PRE_ANSWER}:
            lines = ["ANSWER: 요청 조건에 맞는 후보를 Evidence 기준으로 정리했습니다."]
            for bundle in context.evidence_bundles[:5]:
                metric = bundle.used_fields[0].value if bundle.used_fields else "n/a"
                unit = bundle.used_fields[0].unit if bundle.used_fields else ""
                name = bundle.product_name or "name=n/a"
                lines.append(f"- {bundle.product_uid} / {name} / metric={metric}{unit or ''}")
            for relation in context.relation_evidence[:5]:
                lines.append(
                    f"- {relation.relation_type}: {relation.subject_entity_id}"
                    f" ↔ {relation.object_entity_id}"
                )
            if context.decision.warnings:
                lines.append(f"한계: {'; '.join(context.decision.warnings[:2])}")
            return "\n".join(lines)

        return "ABSTAIN: unsupported decision state"

    async def healthcheck(self) -> dict[str, str]:
        return {"provider": "mock", "status": "ok"}

    async def regenerate_answer(self, context: object, guard_reasons: list[str]) -> str:
        return await self.generate_answer(context)
