"""Small deterministic retrieval for Planner context; no embeddings or RAG."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from agent.intelligence.models import Confidence, Priority
from agent.intelligence.store import IntelligenceStore


def _keywords(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_./-]{2,}", value)
        if token.lower() not in {"the", "and", "for", "with", "from", "this", "that"}
    }


@dataclass(frozen=True)
class IntelligenceContext:
    query: str
    facts: List[Dict[str, Any]]
    hypotheses: List[Dict[str, Any]]
    failed_attempts: List[Dict[str, Any]]
    findings: List[Dict[str, Any]]
    attack_surface: List[Dict[str, Any]]
    open_questions: List[Dict[str, Any]]
    credentials: List[Dict[str, Any]]
    endpoint_findings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IntelligenceRetriever:
    """Select a compact, relevant state view rather than serializing all state."""

    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def retrieve(
        self,
        query: str,
        *,
        categories: Iterable[str] = (),
        limit: int = 12,
    ) -> IntelligenceContext:
        category_set = {category.lower() for category in categories}
        query_tokens = _keywords(query)
        return IntelligenceContext(
            query=query,
            facts=self._rank(
                self.store.state.facts,
                query_tokens,
                category_set,
                lambda item: f"{item.category} {item.content}",
                limit,
            ),
            hypotheses=self._rank(
                self.store.state.hypotheses,
                query_tokens,
                category_set,
                lambda item: item.statement,
                limit,
            ),
            failed_attempts=self._rank(
                self.store.state.failed_attempts,
                query_tokens,
                category_set,
                lambda item: " ".join(
                    [item.category, item.target, item.method, item.input_payload, item.reason]
                ),
                limit,
            ),
            findings=self._rank(
                self.store.state.findings,
                query_tokens,
                category_set,
                lambda item: f"{item.title} {item.description}",
                limit,
            ),
            attack_surface=self._rank(
                self.store.state.attack_surface,
                query_tokens,
                category_set,
                lambda item: " ".join([item.category, item.target, item.method, *item.parameters]),
                limit,
            ),
            endpoint_findings=self._rank(
                self.store.state.endpoint_findings,
                query_tokens,
                category_set,
                lambda item: " ".join(
                    [item.path, item.method, item.source, *item.parameters]
                ),
                limit,
            ),
            open_questions=self._rank(
                self.store.state.open_questions,
                query_tokens,
                category_set,
                lambda item: item.question,
                limit,
            ),
            credentials=[credential.safe_dict() for credential in self.store.state.credentials[:limit]],
        )

    @staticmethod
    def _rank(
        items: Sequence[Any],
        query_tokens: set[str],
        categories: set[str],
        text_for: Any,
        limit: int,
    ) -> List[Dict[str, Any]]:
        scored: List[Tuple[int, int, Dict[str, Any]]] = []
        for index, item in enumerate(items):
            text = text_for(item)
            tokens = _keywords(text)
            category = str(getattr(item, "category", "")).lower()
            overlap = len(query_tokens & tokens)
            category_bonus = 2 if category and category in categories else 0
            importance = getattr(item, "importance", None)
            confidence = getattr(item, "confidence", None)
            certainty_bonus = 1 if importance is Priority.HIGH or confidence is Confidence.CONFIRMED else 0
            if query_tokens and overlap == 0 and category_bonus == 0:
                continue
            scored.append((overlap + category_bonus + certainty_bonus, index, asdict(item)))
        scored.sort(key=lambda value: (value[0], value[1]), reverse=True)
        return [item for _, _, item in scored[:limit]]
