"""Atomic JSON persistence for global R7 experience memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Mapping

from agent.experience.models import ExperienceRecord


DEFAULT_EXPERIENCE_PATH = Path("experiences/global/experience.json")


class ExperienceStore:
    """Own reusable experience records outside per-run checkpoints."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path = DEFAULT_EXPERIENCE_PATH) -> None:
        self.path = Path(path)
        self._records: List[ExperienceRecord] = []
        if self.path.is_file():
            self._load()

    def add(self, record: ExperienceRecord) -> ExperienceRecord:
        if not isinstance(record, ExperienceRecord):
            raise TypeError("record must be an ExperienceRecord")
        existing = self.get(record.id)
        if existing is not None:
            if self._semantic_key(existing) == self._semantic_key(record):
                return existing
            raise ValueError(f"duplicate experience id: {record.id}")
        duplicate = next(
            (
                item
                for item in self._records
                if item.source_run == record.source_run
                and item.domain == record.domain
                and item.category == record.category
                and item.pattern == record.pattern
            ),
            None,
        )
        if duplicate is not None:
            return duplicate
        self._records.append(record)
        self._persist()
        return record

    def add_many(self, records: Iterable[ExperienceRecord]) -> List[ExperienceRecord]:
        added: List[ExperienceRecord] = []
        for record in records:
            known_ids = {item.id for item in self._records}
            stored = self.add(record)
            if stored.id not in known_ids:
                added.append(stored)
        return added

    def list(self) -> List[ExperienceRecord]:
        return list(self._records)

    def get(self, experience_id: str) -> ExperienceRecord | None:
        return next(
            (item for item in self._records if item.id == experience_id),
            None,
        )

    def query(
        self,
        *,
        domain: str | None = None,
        category: str | None = None,
        keywords: Iterable[str] = (),
        limit: int | None = None,
    ) -> List[ExperienceRecord]:
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0
        ):
            raise ValueError("limit must be an integer > 0")
        required = [item.strip().lower() for item in keywords if item.strip()]
        matches: List[ExperienceRecord] = []
        for record in self._records:
            if domain is not None and record.domain != domain.strip().lower():
                continue
            if category is not None and record.category != category.strip().lower():
                continue
            searchable = " ".join(
                [
                    record.domain,
                    record.category,
                    record.trigger,
                    record.pattern,
                    record.strategy,
                    record.lesson,
                    record.failure,
                ]
            ).lower()
            if required and not all(keyword in searchable for keyword in required):
                continue
            matches.append(record)
        return matches[:limit] if limit is not None else matches

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("experience JSON must contain an object")
        if raw.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("unsupported experience store schema version")
        items = raw.get("experiences")
        if not isinstance(items, list):
            raise ValueError("experience JSON experiences must contain an array")
        if not all(isinstance(item, Mapping) for item in items):
            raise ValueError("every experience JSON entry must be an object")
        records = [
            ExperienceRecord.from_dict(item)
            for item in items
        ]
        ids = {item.id for item in records}
        if len(ids) != len(records):
            raise ValueError("duplicate experience id in store")
        self._records = records

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "experiences": [item.to_dict() for item in self._records],
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _semantic_key(record: ExperienceRecord) -> tuple[object, ...]:
        return (
            record.domain,
            record.category,
            record.trigger,
            record.pattern,
            record.strategy,
            record.lesson,
            record.failure,
            record.source_run,
            record.confidence,
        )
