"""Policy Engine과 Agent 오케스트레이션 — Step 07"""

from app.agent.decision import Decision, DecisionState
from app.agent.execution_plan import ExecutionPlan, RetrieverKind

__all__ = [
    "Decision",
    "DecisionState",
    "ExecutionPlan",
    "RetrieverKind",
]


def __getattr__(name: str) -> object:
    if name in {"AgentOrchestrator", "AgentRunResult", "finalize_decision"}:
        from app.agent.orchestrator import AgentOrchestrator, AgentRunResult, finalize_decision

        exports = {
            "AgentOrchestrator": AgentOrchestrator,
            "AgentRunResult": AgentRunResult,
            "finalize_decision": finalize_decision,
        }
        return exports[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
