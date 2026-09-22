"""Deterministic ChallengeSpec-to-domain-and-skill routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agent.domains.base import DomainMatch
from agent.domains.base.rules import challenge_text, contains_signal
from agent.domains.loader import SkillLoader
from agent.domains.registry import DomainRegistry, build_default_domain_registry
from agent.runtime.contracts import ChallengeSpec


@dataclass(frozen=True)
class DomainSelection:
    selected_domains: tuple[str, ...]
    selected_skills: tuple[str, ...]
    confidence: float
    matches: tuple[DomainMatch, ...]
    rationale: tuple[str, ...]

    @property
    def primary_domain(self) -> str:
        return self.selected_domains[0]


class SkillRouter:
    """Route using local rules only: no LLM, embeddings, network, or tools."""

    def __init__(
        self,
        registry: DomainRegistry | None = None,
        loader: SkillLoader | None = None,
        *,
        default_domain: str = "auto",
        threshold: float = 0.24,
    ) -> None:
        self.registry = registry or build_default_domain_registry()
        self.loader = loader or SkillLoader()
        self.default_domain = str(default_domain or "auto").strip().lower()
        self.threshold = threshold
        if self.default_domain != "auto" and self.default_domain not in self.registry.names():
            raise ValueError(f"unknown configured default domain: {self.default_domain}")

    def route(
        self,
        challenge: ChallengeSpec,
        artifact_metadata: Sequence[Mapping[str, Any]] = (),
    ) -> DomainSelection:
        matches = tuple(
            domain.detect(challenge, artifact_metadata) for domain in self.registry.all()
        )
        if self.default_domain != "auto":
            selected_matches = [
                next(match for match in matches if match.domain == self.default_domain)
            ]
            confidence = 1.0
            rationale = (f"configured default domain:{self.default_domain}",)
        else:
            ranked = sorted(
                (match for match in matches if match.domain != "misc"),
                key=lambda match: (-match.confidence, self.registry.names().index(match.domain)),
            )
            selected_matches = [match for match in ranked if match.confidence >= self.threshold][:2]
            if not selected_matches:
                selected_matches = [next(match for match in matches if match.domain == "misc")]
                confidence = max(0.25, selected_matches[0].confidence)
                rationale = ("no stronger deterministic signal; misc fallback",)
            else:
                confidence = selected_matches[0].confidence
                rationale = tuple(
                    f"{match.domain}: {', '.join(match.signals) or 'matched skill metadata'}"
                    for match in selected_matches
                )

        selected_skills = self._select_skills(
            challenge,
            artifact_metadata,
            selected_matches,
        )
        return DomainSelection(
            selected_domains=tuple(match.domain for match in selected_matches),
            selected_skills=selected_skills,
            confidence=min(1.0, confidence),
            matches=matches,
            rationale=rationale,
        )

    def _select_skills(
        self,
        challenge: ChallengeSpec,
        artifact_metadata: Sequence[Mapping[str, Any]],
        selected_matches: Sequence[DomainMatch],
    ) -> tuple[str, ...]:
        text = challenge_text(challenge, artifact_metadata)
        available = self.loader.load()
        selected: list[str] = []
        for match in selected_matches:
            domain = self.registry.get(match.domain)
            base_name = domain.skill_names[0]
            candidates = [base_name, *match.matched_skills]
            for skill in self.loader.for_domain(domain.name):
                if skill.name == base_name:
                    continue
                if any(contains_signal(text, tag) for tag in skill.tags):
                    candidates.append(skill.name)
            for name in candidates:
                if name in available and name not in selected:
                    domain.get_skill(self.loader, name)
                    selected.append(name)
        return tuple(selected[:6])


# The descriptive R3 name remains available to avoid ambiguity with the R2
# compatibility router while the public R3 contract is named SkillRouter.
DomainSkillRouter = SkillRouter
