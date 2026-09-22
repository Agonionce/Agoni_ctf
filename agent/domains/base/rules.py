"""Shared deterministic matching for concrete R3 domains."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agent.domains.base.contracts import Domain, DomainMatch
from agent.runtime.contracts import ChallengeSpec


def challenge_text(
    challenge: ChallengeSpec,
    artifact_metadata: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Build a normalized classification view without reading artifact files."""

    metadata = json.dumps(challenge.metadata, ensure_ascii=False, default=str)
    artifacts = json.dumps(list(artifact_metadata), ensure_ascii=False, default=str)
    return " ".join(
        filter(
            None,
            [
                challenge.title,
                challenge.description,
                challenge.category or "",
                metadata,
                artifacts,
            ],
        )
    ).lower()


def contains_signal(text: str, signal: str) -> bool:
    signal = signal.lower()
    if re.fullmatch(r"[a-z0-9_+-]+", signal):
        return re.search(rf"(?<![a-z0-9_]){re.escape(signal)}(?![a-z0-9_])", text) is not None
    return signal in text


@dataclass(frozen=True)
class RuleDomain(Domain):
    """Small keyword classifier; it performs no LLM or external lookup."""

    name: str
    description: str
    skill_names: tuple[str, ...]
    signals: tuple[str, ...]
    skill_signals: Mapping[str, tuple[str, ...]]

    def detect(
        self,
        challenge: ChallengeSpec,
        artifact_metadata: Sequence[Mapping[str, Any]] = (),
    ) -> DomainMatch:
        text = challenge_text(challenge, artifact_metadata)
        explicit_category = (challenge.category or "").strip().lower() == self.name
        matched = tuple(signal for signal in self.signals if contains_signal(text, signal))
        skill_matches = tuple(
            skill_name
            for skill_name, signals in self.skill_signals.items()
            if any(contains_signal(text, signal) for signal in signals)
        )
        score = (0.65 if explicit_category else 0.0) + min(0.6, len(matched) * 0.15)
        if skill_matches and not matched:
            score += min(0.45, len(skill_matches) * 0.15)
        return DomainMatch(
            domain=self.name,
            confidence=min(1.0, score),
            signals=(("category:" + self.name,) if explicit_category else ()) + matched,
            matched_skills=skill_matches,
        )
