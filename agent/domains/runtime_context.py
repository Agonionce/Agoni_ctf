"""Planner context composition for R4 lifecycle state."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domains.base.runtime import DomainRuntime, DomainRuntimeState
from agent.runtime.contracts import ChallengeSpec


class DomainRuntimeContextBuilder:
    """Combine bounded R4 state with already-filtered R3/R2 context."""

    INTELLIGENCE_KEYS = (
        "facts",
        "hypotheses",
        "failed_attempts",
        "findings",
        "attack_surface",
        "open_questions",
    )

    def __init__(self, *, max_items_per_collection: int = 3) -> None:
        self.max_items_per_collection = max_items_per_collection

    def build(
        self,
        challenge: ChallengeSpec,
        runtime: DomainRuntime,
        state: DomainRuntimeState,
        skill_context: Mapping[str, Any],
        intelligence_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        routing = skill_context.get("routing", {})
        selected_skills = skill_context.get("skills", [])
        bounded_intelligence: dict[str, Any] = {}
        if intelligence_context:
            for key in self.INTELLIGENCE_KEYS:
                value = intelligence_context.get(key)
                if isinstance(value, list) and value:
                    bounded_intelligence[key] = value[: self.max_items_per_collection]
        return {
            "challenge": {
                "challenge_id": challenge.challenge_id,
                "title": challenge.title,
                "category": challenge.category,
            },
            "domain_runtime": runtime.generate_context(state),
            "skill_context": {
                "routing": dict(routing) if isinstance(routing, Mapping) else {},
                "skills": list(selected_skills) if isinstance(selected_skills, list) else [],
            },
            "relevant_intelligence": bounded_intelligence,
        }
