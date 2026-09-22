"""Build compact Planner context from selected R3 skills and R2 intelligence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from agent.domains.base import Skill
from agent.domains.router import DomainSelection
from agent.runtime.contracts import ChallengeSpec


class SkillContextBuilder:
    """Inject only selected skills and a bounded relevant intelligence view."""

    INTELLIGENCE_KEYS = (
        "facts",
        "hypotheses",
        "failed_attempts",
        "findings",
        "attack_surface",
        "open_questions",
    )

    def __init__(self, *, max_skills: int = 6, max_items_per_collection: int = 3) -> None:
        self.max_skills = max_skills
        self.max_items_per_collection = max_items_per_collection

    def build(
        self,
        challenge: ChallengeSpec,
        selection: DomainSelection,
        skills: Sequence[Skill],
        intelligence_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        selected_names = set(selection.selected_skills)
        relevant_skills = [skill for skill in skills if skill.name in selected_names]
        relevant_skills.sort(key=lambda skill: selection.selected_skills.index(skill.name))
        skill_context = [
            {
                "name": skill.name,
                "domain": skill.domain,
                "description": skill.description,
                "knowledge": list(skill.knowledge[:6]),
                "strategies": list(skill.strategies[:6]),
                "heuristics": list(skill.heuristics[:4]),
            }
            for skill in relevant_skills[: self.max_skills]
        ]
        intelligence: dict[str, Any] = {}
        if intelligence_context:
            for key in self.INTELLIGENCE_KEYS:
                value = intelligence_context.get(key)
                if isinstance(value, list) and value:
                    intelligence[key] = value[: self.max_items_per_collection]
        return {
            "challenge": {
                "challenge_id": challenge.challenge_id,
                "title": challenge.title,
                "category": challenge.category,
            },
            "routing": {
                "domains": list(selection.selected_domains),
                "skills": list(selection.selected_skills),
                "confidence": round(selection.confidence, 3),
                "rationale": list(selection.rationale),
            },
            "skills": skill_context,
            "relevant_intelligence": intelligence,
        }
