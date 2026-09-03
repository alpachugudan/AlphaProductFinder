from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.config.settings import PROJECT_ROOT, Settings
from app.evidence.models import AnswerContext, EvidenceBundle
from app.llm.client import HcxCompletion, HcxHttpClient
from app.llm.errors import HcxResponseError
from app.query.enums import (
    AsOfRequirement,
    Direction,
    EntityType,
    Intent,
    MissingPolicy,
    Operator,
    ProductFamily,
    RelationType,
)
from app.query.korean_rule_parser import parse_korean_finance_question
from app.query.models import QuerySpec
from app.query.registry import get_field_registry

PROMPT_DIR = PROJECT_ROOT / "app" / "llm" / "prompts"
QUERY_SYSTEM_PROMPT = (PROMPT_DIR / "queryspec_system_v1.txt").read_text(encoding="utf-8")
ANSWER_SYSTEM_PROMPT = (PROMPT_DIR / "answer_system_v1.txt").read_text(encoding="utf-8")
logger = logging.getLogger(__name__)


class HyperClovaProvider:
    """HCX-007 provider: schema-constrained QuerySpec then evidence-bounded answer."""

    prompt_version: str

    def __init__(self, settings: Settings, *, client: HcxHttpClient | None = None) -> None:
        self._settings = settings
        self._client = client or HcxHttpClient(settings)
        self.prompt_version = settings.hcx_prompt_version

    async def parse_query(self, question: str) -> QuerySpec:
        """Parse only the transport/schema contract.

        A syntactically valid but semantically incomplete QuerySpec is not an HCX
        failure.  The policy engine deliberately turns those cases into ASK or
        ABSTAIN decisions after parsing.  Rejecting them here made normal
        clarification requests look like a 503 and needlessly repeated a
        billable HCX request.
        """
        if spec := parse_korean_finance_question(question):
            logger.info(
                "Korean rule parser produced QuerySpec",
                extra={
                    "intent": spec.intent.value,
                    "families": [family.value for family in spec.product_families],
                },
            )
            return spec

        correction = False
        correction_issues: list[str] = []
        for attempt in range(2):
            completion = await self._client.complete(
                model=self._settings.hcx_intent_model,
                payload=self._queryspec_payload(
                    question,
                    correction=correction,
                    correction_issues=correction_issues,
                ),
            )
            try:
                return QuerySpec.model_validate_json(completion.content)
            except ValidationError as exc:
                correction_issues = _validation_error_summary(exc)
                logger.warning(
                    "HCX QuerySpec schema validation failed",
                    extra={
                        "attempt": attempt + 1,
                        "validation_issue_count": len(correction_issues),
                        "validation_issues": correction_issues,
                    },
                )
                correction = True
        raise HcxResponseError()

    async def generate_answer(self, context: object) -> str:
        if not isinstance(context, AnswerContext):
            msg = "generate_answer expects AnswerContext"
            raise TypeError(msg)
        completion = await self._client.complete(
            model=self._settings.hcx_answer_model,
            payload=self._answer_payload(context),
        )
        return completion.content.strip()

    async def regenerate_answer(self, context: object, guard_reasons: list[str]) -> str:
        if not isinstance(context, AnswerContext):
            msg = "regenerate_answer expects AnswerContext"
            raise TypeError(msg)
        completion = await self._client.complete(
            model=self._settings.hcx_answer_model,
            payload=self._answer_payload(context, guard_reasons=guard_reasons),
        )
        return completion.content.strip()

    async def healthcheck(self) -> dict[str, str]:
        """Readiness is configuration-only; no billable generation happens here."""
        has_key = self._settings.hcx_api_key is not None and bool(
            self._settings.hcx_api_key.get_secret_value().strip()
        )
        return {
            "provider": "hyperclova",
            "status": "ok" if has_key else "unavailable",
            "billing_mode": self._settings.billing_mode,
        }

    async def capability_smoke(self) -> dict[str, HcxCompletion]:
        """Evaluation-start low-token proof. Invoked once, never by /health/ready."""
        query = await self._client.complete(
            model=self._settings.hcx_intent_model,
            payload=self._queryspec_payload("향후 수익률을 예측해줘", correction=False),
        )
        answer = await self._client.complete(
            model=self._settings.hcx_answer_model,
            payload={
                "messages": [
                    {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "required_state=ABSTAIN\n"
                            "question=향후 수익률을 알려줘\n"
                            "evidence=[]\n"
                            "Write one short sentence."
                        ),
                    },
                ],
                "topP": 0.8,
                "topK": 0,
                "maxCompletionTokens": 32,
                "temperature": 0.0,
                "repetitionPenalty": 1.1,
                "thinking": {"effort": "none"},
            },
        )
        return {"query": query, "answer": answer}

    def _queryspec_payload(
        self,
        question: str,
        *,
        correction: bool,
        correction_issues: list[str] | None = None,
    ) -> dict[str, Any]:
        correction_message = ""
        if correction:
            issue_text = ", ".join(correction_issues or ["unknown schema error"])
            correction_message = (
                "\nThe prior output failed JSON Schema validation. Return the complete JSON object "
                "again with no extra keys. Correct these locations/types: "
                f"{issue_text}. Every required top-level array must be present, even when empty."
            )
        return {
            "messages": [
                {"role": "system", "content": QUERY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"question={question}{correction_message}",
                },
            ],
            "topP": 0.8,
            "topK": 0,
            "maxCompletionTokens": 256,
            "temperature": 0.0,
            "repetitionPenalty": 1.1,
            # HCX-007 Structured Outputs accepts effort=none. This disables inference;
            # never enable low/medium/high thinking together with responseFormat.
            "thinking": {"effort": "none"},
            "responseFormat": {"type": "json", "schema": _queryspec_schema()},
        }

    def _answer_payload(
        self,
        context: AnswerContext,
        *,
        guard_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "question": context.question,
            "queryspec": context.spec_summary,
            "decision": {
                "state": context.decision.state.value,
                "reason_codes": [item.value for item in context.decision.reason_codes],
                "missing_requirements": context.decision.missing_requirements,
                "warnings": context.decision.warnings,
            },
            "evidence": [_serialize_bundle(bundle) for bundle in context.evidence_bundles],
            "relation_evidence": [
                {
                    "relation_type": item.relation_type,
                    "subject_entity_id": item.subject_entity_id,
                    "object_entity_id": item.object_entity_id,
                    "source_document_id": item.source_document_id,
                    "as_of_date": item.as_of_date,
                }
                for item in context.relation_evidence
            ],
            "required_prefix": f"{context.decision.state.value}:",
            "forbidden_phrases": context.forbidden_phrases,
            "non_negotiable_instruction": (
                f"The first characters of the answer must be {context.decision.state.value}: "
                "and no other state prefix is allowed."
            ),
        }
        if guard_reasons:
            payload["guard_correction"] = {
                "failed_reasons": guard_reasons,
                "instruction": "Regenerate using evidence only and remove every failed pattern.",
            }
        return {
            "messages": [
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "STRICT OUTPUT: Start the entire answer exactly with "
                        f"{context.decision.state.value}: using ASCII letters and colon. "
                        "Never start with Korean labels such as 답변:, 응답:, 결과:.\n"
                        "INPUT_JSON="
                        + json.dumps(payload, ensure_ascii=False, default=str)
                    ),
                },
            ],
            "topP": 0.8,
            "topK": 0,
            "maxCompletionTokens": 256,
            "temperature": 0.0,
            "repetitionPenalty": 1.1,
            "thinking": {"effort": "none"},
        }


def _serialize_bundle(bundle: EvidenceBundle) -> dict[str, Any]:
    return {
        "product_uid": bundle.product_uid,
        "product_name": bundle.product_name,
        "source_table": bundle.source_table,
        "used_fields": [
            {
                "logical_field": field.logical_field,
                "value": field.value,
                "unit": field.unit,
                "as_of_date": field.as_of_date,
                "quality_flags": field.quality_flags,
            }
            for field in bundle.used_fields
        ],
        "quality_flags": bundle.quality_flags,
        "selection_reasons": bundle.selection_reasons,
    }


def _queryspec_schema() -> dict[str, Any]:
    """NCP Structured Outputs subset: no refs, null type, defaults, or unsupported keywords."""
    field_ids = list(get_field_registry().fields)
    scalar_or_collection: dict[str, Any] = {
        "anyOf": [
            {"type": "string"},
            {"type": "number"},
            {"type": "integer"},
            {"type": "boolean"},
            {"type": "array", "items": {}},
            {"type": "object", "properties": {}},
        ]
    }
    direction = {"type": "string", "enum": [item.value for item in Direction]}
    return {
        "type": "object",
        "properties": {
            "version": {"type": "string"},
            "intent": {"type": "string", "enum": [item.value for item in Intent]},
            "product_families": {
                "type": "array",
                "items": {"type": "string", "enum": [item.value for item in ProductFamily]},
                "maxItems": 4,
            },
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "entity_type": {
                            "type": "string",
                            "enum": [item.value for item in EntityType],
                        },
                    },
                    "required": ["text", "entity_type"],
                },
            },
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": field_ids},
                        "operator": {
                            "type": "string",
                            "enum": [item.value for item in Operator],
                        },
                        "value": scalar_or_collection,
                    },
                    "required": ["field", "operator"],
                },
            },
            "relationship_filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "relation": {
                            "type": "string",
                            "enum": [item.value for item in RelationType],
                        },
                        "target_entity": {"type": "string"},
                    },
                    "required": ["relation", "target_entity"],
                },
            },
            "metrics": {"type": "array", "items": {"type": "string", "enum": field_ids}},
            "preferences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": field_ids},
                        "direction": direction,
                        "priority": {"type": "integer", "minimum": 1},
                    },
                    "required": ["field", "direction"],
                },
            },
            "sort": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": field_ids},
                        "direction": direction,
                    },
                    "required": ["field", "direction"],
                },
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            "as_of_requirement": {
                "type": "string",
                "enum": [item.value for item in AsOfRequirement],
            },
            "missing_policy": {
                "type": "string",
                "enum": [item.value for item in MissingPolicy],
            },
        },
        "required": [
            "version",
            "intent",
            "product_families",
            "entities",
            "filters",
            "relationship_filters",
            "metrics",
            "preferences",
            "sort",
            "limit",
            "as_of_requirement",
            "missing_policy",
        ],
    }


def _validation_error_summary(exc: ValidationError) -> list[str]:
    """Return location/type only; never put HCX content or user text into logs."""
    summaries: list[str] = []
    for item in exc.errors(include_input=False):
        location = ".".join(str(part) for part in item.get("loc", ())) or "root"
        error_type = str(item.get("type", "validation_error"))
        summaries.append(f"{location}:{error_type}")
    return summaries[:12]
