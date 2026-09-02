from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.reason_codes import DecisionState, ReasonCode

__all__ = ["Decision", "DecisionState", "ReasonCode"]


@dataclass(slots=True)
class Decision:
    state: DecisionState
    reason_codes: list[ReasonCode] = field(default_factory=list)
    user_message_requirements: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    selected_candidate_ids: list[str] = field(default_factory=list)
    execution_summary: dict[str, object] = field(default_factory=dict)
