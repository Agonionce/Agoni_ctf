"""R13 auditable quality and effectiveness metadata for approved experience."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from agent.experience.models import ExperienceRecord, utc_now_iso
from agent.experience.store import ExperienceStore


class ExperienceFeedbackOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"


def _opaque(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if re.fullmatch(r"[A-Za-z0-9._:-]+", normalized) is None:
        raise ValueError(f"{field_name} must be an opaque normalized identifier")
    return normalized


@dataclass(frozen=True)
class ExperienceFeedbackRecord:
    feedback_id: str
    experience_id: str
    source_run: str
    source_challenge: str
    outcome: ExperienceFeedbackOutcome
    solved: bool
    evidence_refs: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        for name in ("feedback_id", "experience_id", "source_run", "source_challenge"):
            object.__setattr__(self, name, _opaque(getattr(self, name), name))
        if not isinstance(self.outcome, ExperienceFeedbackOutcome):
            raise ValueError("feedback outcome is invalid")
        object.__setattr__(
            self,
            "evidence_refs",
            tuple(dict.fromkeys(_opaque(item, "evidence_ref") for item in self.evidence_refs))[:64],
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        payload["evidence_refs"] = list(self.evidence_refs)
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExperienceFeedbackRecord":
        raw_refs = data.get("evidence_refs", [])
        return cls(
            feedback_id=str(data["feedback_id"]),
            experience_id=str(data["experience_id"]),
            source_run=str(data["source_run"]),
            source_challenge=str(data["source_challenge"]),
            outcome=ExperienceFeedbackOutcome(str(data["outcome"])),
            solved=bool(data.get("solved", False)),
            evidence_refs=(
                tuple(str(item) for item in raw_refs)
                if isinstance(raw_refs, list)
                else ()
            ),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class ExperienceQualityRecord:
    experience_id: str
    source_challenge: str
    source_evidence: list[str]
    confidence: float
    use_count: int = 0
    validation_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    inconclusive_count: int = 0
    effectiveness: float = 0.5
    feedback_ids: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.experience_id = _opaque(self.experience_id, "experience_id")
        self.source_challenge = _opaque(self.source_challenge, "source_challenge")
        self.source_evidence = list(dict.fromkeys(
            _opaque(item, "source_evidence") for item in self.source_evidence
        ))[:64]
        for name in (
            "use_count", "validation_count", "success_count",
            "failure_count", "inconclusive_count",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in ("confidence", "effectiveness"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
            setattr(self, name, float(value))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExperienceQualityRecord":
        def strings(name: str) -> list[str]:
            raw = data.get(name, [])
            return [str(item) for item in raw] if isinstance(raw, list) else []

        return cls(
            experience_id=str(data["experience_id"]),
            source_challenge=str(data["source_challenge"]),
            source_evidence=strings("source_evidence"),
            confidence=float(data.get("confidence", 0.5)),
            use_count=int(data.get("use_count", 0)),
            validation_count=int(data.get("validation_count", 0)),
            success_count=int(data.get("success_count", 0)),
            failure_count=int(data.get("failure_count", 0)),
            inconclusive_count=int(data.get("inconclusive_count", 0)),
            effectiveness=float(data.get("effectiveness", 0.5)),
            feedback_ids=strings("feedback_ids"),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )


class ExperienceQualityStore:
    """Separate quality metadata; approved experience text remains immutable."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._records: dict[str, ExperienceQualityRecord] = {}
        self._feedback: list[ExperienceFeedbackRecord] = []
        if self.path.is_file():
            self._load()

    @classmethod
    def for_experience_path(cls, experience_path: str | Path) -> "ExperienceQualityStore":
        path = Path(experience_path)
        return cls(path.with_name("experience-quality.json"))

    def get(self, experience_id: str) -> ExperienceQualityRecord | None:
        return self._records.get(experience_id)

    def list(self) -> list[ExperienceQualityRecord]:
        return sorted(self._records.values(), key=lambda item: item.experience_id)

    def feedback(self, experience_id: str | None = None) -> list[ExperienceFeedbackRecord]:
        return [
            item for item in self._feedback
            if experience_id is None or item.experience_id == experience_id
        ]

    def ensure(
        self,
        experience: ExperienceRecord,
        *,
        source_challenge: str | None = None,
        source_evidence: tuple[str, ...] = (),
    ) -> ExperienceQualityRecord:
        existing = self.get(experience.id)
        if existing is not None:
            merged = list(dict.fromkeys([*existing.source_evidence, *source_evidence]))[:64]
            if merged != existing.source_evidence:
                existing.source_evidence = merged
                existing.updated_at = utc_now_iso()
                self._persist()
            return existing
        record = ExperienceQualityRecord(
            experience_id=experience.id,
            source_challenge=source_challenge or experience.source_run,
            source_evidence=list(source_evidence),
            confidence=experience.confidence,
        )
        self._records[record.experience_id] = record
        self._persist()
        return record

    def record_feedback(
        self,
        experience: ExperienceRecord,
        *,
        source_run: str,
        source_challenge: str,
        outcome: ExperienceFeedbackOutcome,
        solved: bool,
        evidence_refs: tuple[str, ...] = (),
    ) -> ExperienceQualityRecord:
        quality = self.ensure(experience)
        key = (
            f"{experience.id}\0{source_run}\0{source_challenge}"
        )
        feedback_id = "feedback-" + hashlib.sha256(key.encode()).hexdigest()[:12]
        if any(item.feedback_id == feedback_id for item in self._feedback):
            return quality
        feedback = ExperienceFeedbackRecord(
            feedback_id=feedback_id,
            experience_id=experience.id,
            source_run=source_run,
            source_challenge=source_challenge,
            outcome=outcome,
            solved=solved,
            evidence_refs=evidence_refs,
        )
        self._feedback.append(feedback)
        quality.use_count += 1
        quality.validation_count += 1
        if outcome is ExperienceFeedbackOutcome.SUCCESS:
            quality.success_count += 1
            quality.confidence = min(1.0, quality.confidence + 0.05 * (1.0 - quality.confidence))
        elif outcome is ExperienceFeedbackOutcome.FAILURE:
            quality.failure_count += 1
            quality.confidence = max(0.0, quality.confidence - 0.05 * quality.confidence)
        else:
            quality.inconclusive_count += 1
        decisive = quality.success_count + quality.failure_count
        quality.effectiveness = (
            quality.success_count / decisive if decisive else 0.5
        )
        quality.feedback_ids.append(feedback.feedback_id)
        quality.updated_at = feedback.created_at
        self._persist()
        return quality

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping) or raw.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("unsupported experience quality schema version")
        records = raw.get("records", [])
        feedback = raw.get("feedback", [])
        if not isinstance(records, list) or not isinstance(feedback, list):
            raise ValueError("experience quality collections must be arrays")
        if not all(isinstance(item, Mapping) for item in [*records, *feedback]):
            raise ValueError("experience quality entries must be objects")
        loaded = [
            ExperienceQualityRecord.from_dict(item)
            for item in records
        ]
        if len({item.experience_id for item in loaded}) != len(loaded):
            raise ValueError("duplicate Experience quality ID")
        self._records = {item.experience_id: item for item in loaded}
        self._feedback = [
            ExperienceFeedbackRecord.from_dict(item)
            for item in feedback
        ]
        if len({item.feedback_id for item in self._feedback}) != len(self._feedback):
            raise ValueError("duplicate Experience feedback ID")
        if any(item.experience_id not in self._records for item in self._feedback):
            raise ValueError("Experience feedback references unknown quality state")

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps({
                "schema_version": self.SCHEMA_VERSION,
                "records": [item.to_dict() for item in self.list()],
                "feedback": [item.to_dict() for item in self._feedback],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


class ExperienceFeedbackManager:
    """Bind explicit run feedback to an existing approved experience record."""

    def __init__(
        self,
        experience_store: ExperienceStore,
        quality_store: ExperienceQualityStore,
    ) -> None:
        self.experience_store = experience_store
        self.quality_store = quality_store

    def record(
        self,
        experience_id: str,
        *,
        source_run: str,
        source_challenge: str,
        outcome: ExperienceFeedbackOutcome,
        solved: bool,
        evidence_refs: tuple[str, ...] = (),
    ) -> ExperienceQualityRecord:
        experience = self.experience_store.get(experience_id)
        if experience is None:
            raise ValueError(f"unknown approved experience ID: {experience_id}")
        return self.quality_store.record_feedback(
            experience,
            source_run=source_run,
            source_challenge=source_challenge,
            outcome=outcome,
            solved=solved,
            evidence_refs=evidence_refs,
        )
