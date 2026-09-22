"""Deterministic R7 experience retrieval without embeddings or vector search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from agent.experience.models import ExperienceRecord
from agent.experience.quality import ExperienceQualityStore
from agent.experience.store import ExperienceStore
from agent.runtime.contracts import ChallengeSpec


def _tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    ignored = {"the", "and", "for", "with", "from", "this"}
    for raw in re.findall(r"[A-Za-z0-9_-]{2,}", value):
        normalized = raw.lower()
        if normalized not in ignored:
            tokens.add(normalized)
        tokens.update(
            part
            for part in re.split(r"[_-]+", normalized)
            if len(part) >= 2 and part not in ignored
        )
    return tokens


@dataclass(frozen=True)
class ExperienceContext:
    relevant_experience: list[dict[str, Any]]
    limit: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevant_experience": list(self.relevant_experience),
            "limit": self.limit,
        }


class ExperienceRetriever:
    """Rank global experience using domain, category, skill, and keyword rules."""

    def __init__(
        self,
        store: ExperienceStore,
        quality_store: ExperienceQualityStore | None = None,
    ) -> None:
        self.store = store
        self.quality_store = quality_store

    def retrieve(
        self,
        challenge: ChallengeSpec,
        *,
        domain: str | None = None,
        skills: Sequence[str] = (),
        artifact_metadata: Sequence[Mapping[str, Any]] = (),
        limit: int = 5,
    ) -> ExperienceContext:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit must be an integer > 0")
        selected_domain = (domain or challenge.category or "").strip().lower()
        query_values = [
            challenge.title,
            challenge.description,
            challenge.category or "",
            selected_domain,
            *skills,
        ]
        for metadata in artifact_metadata:
            query_values.extend(str(value) for value in metadata.values())
        query_tokens = _tokens(" ".join(query_values))
        scored: list[tuple[int, int, ExperienceRecord]] = []
        for index, record in enumerate(self.store.list()):
            record_tokens = _tokens(
                " ".join(
                    [
                        record.domain,
                        record.category,
                        record.trigger,
                        record.pattern,
                        record.strategy,
                        record.lesson,
                        record.failure,
                    ]
                )
            )
            overlap = len(query_tokens & record_tokens)
            domain_score = 5 if selected_domain and record.domain == selected_domain else 0
            category_score = 3 if record.category in query_tokens else 0
            skill_score = 2 if record.category in {item.lower() for item in skills} else 0
            score = domain_score + category_score + skill_score + overlap
            quality = (
                self.quality_store.get(record.id)
                if self.quality_store is not None
                else None
            )
            if quality is not None and quality.validation_count:
                score += int(round(quality.effectiveness * 4))
            if score > 0:
                scored.append((score, index, record))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        records = []
        for _score, _index, item in scored[:limit]:
            payload = item.to_dict()
            quality = (
                self.quality_store.get(item.id)
                if self.quality_store is not None
                else None
            )
            if quality is not None:
                payload["quality"] = {
                    "use_count": quality.use_count,
                    "validation_count": quality.validation_count,
                    "effectiveness": quality.effectiveness,
                    "confidence": quality.confidence,
                }
            records.append(payload)
        return ExperienceContext(records, limit)
