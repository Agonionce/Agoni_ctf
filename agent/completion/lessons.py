"""R13 rule-driven lesson candidates with evidence provenance."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from agent.completion.collector import sanitize_completion_text
from agent.completion.models import ChallengeReport, contains_candidate_sensitive_text


class LessonKind(str, Enum):
    SUCCESSFUL_STRATEGY = "SUCCESSFUL_STRATEGY"
    FAILED_STRATEGY = "FAILED_STRATEGY"
    GENERAL_INSIGHT = "GENERAL_INSIGHT"


@dataclass(frozen=True)
class LessonCandidate:
    lesson_id: str
    kind: LessonKind
    statement: str
    rationale: str
    source_challenge: str
    evidence_refs: tuple[str, ...]
    experiment_refs: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        if re.fullmatch(r"[A-Za-z0-9._:-]+", self.lesson_id) is None:
            raise ValueError("lesson_id must be an opaque identifier")
        if re.fullmatch(r"[A-Za-z0-9._:-]+", self.source_challenge) is None:
            raise ValueError("source_challenge must be an opaque identifier")
        if not isinstance(self.kind, LessonKind):
            raise ValueError("lesson kind is invalid")
        statement = " ".join(self.statement.strip().splitlines())
        rationale = " ".join(self.rationale.strip().splitlines())
        if not statement or not rationale:
            raise ValueError("lesson statement and rationale are required")
        if len(statement) > 1000 or len(rationale) > 1000:
            raise ValueError("lesson text exceeds the size limit")
        if contains_candidate_sensitive_text(statement) or contains_candidate_sensitive_text(
            rationale
        ):
            raise ValueError("lesson candidate contains sensitive terminology")
        object.__setattr__(self, "statement", statement)
        object.__setattr__(self, "rationale", rationale)
        for name in ("evidence_refs", "experiment_refs"):
            values = tuple(dict.fromkeys(str(item) for item in getattr(self, name)))
            if any(re.fullmatch(r"[A-Za-z0-9._:-]+", item) is None for item in values):
                raise ValueError(f"{name} must contain opaque identifiers")
            object.__setattr__(self, name, values)
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ) or not 0 <= self.confidence <= 1:
            raise ValueError("lesson confidence must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["evidence_refs"] = list(self.evidence_refs)
        payload["experiment_refs"] = list(self.experiment_refs)
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LessonCandidate":
        def strings(name: str) -> tuple[str, ...]:
            raw = data.get(name, [])
            return tuple(str(item) for item in raw) if isinstance(raw, list) else ()

        return cls(
            lesson_id=str(data["lesson_id"]),
            kind=LessonKind(str(data["kind"])),
            statement=str(data["statement"]),
            rationale=str(data["rationale"]),
            source_challenge=str(data["source_challenge"]),
            evidence_refs=strings("evidence_refs"),
            experiment_refs=strings("experiment_refs"),
            confidence=float(data["confidence"]),
        )


class LessonExtractor:
    """Extract lessons from persisted report fields without invoking an LLM."""

    MAX_CANDIDATES = 12

    def extract(self, report: ChallengeReport) -> list[LessonCandidate]:
        candidates: list[LessonCandidate] = []
        evidence_by_experiment: dict[str, list[str]] = {}
        for item in report.evidence:
            experiment_id = str(item.get("experiment_id", ""))
            references = self._references(item)
            evidence_id = str(item.get("evidence_id", ""))
            if evidence_id:
                references.append(evidence_id)
            if experiment_id:
                evidence_by_experiment.setdefault(experiment_id, []).extend(references)
        for item in report.experiments:
            experiment_id = str(item.get("experiment_id", ""))
            goal = sanitize_completion_text(item.get("goal", "")).strip()
            status = str(item.get("status", "")).upper()
            if not goal or contains_candidate_sensitive_text(goal):
                continue
            if status in {"SUCCESS", "COMPLETED"}:
                kind = LessonKind.SUCCESSFUL_STRATEGY
                statement = f"The bounded strategy '{goal}' produced a supported result."
                rationale = "Expected and actual observations aligned in the persisted experiment timeline."
                confidence = 0.78
            elif status == "FAILED":
                kind = LessonKind.FAILED_STRATEGY
                statement = f"The bounded strategy '{goal}' did not produce its expected observation."
                rationale = "The failed result should prevent repetition without new discriminating evidence."
                confidence = 0.72
            else:
                continue
            candidate = self._candidate(
                report,
                kind,
                statement,
                rationale,
                evidence_by_experiment.get(experiment_id, []),
                [experiment_id] if experiment_id else [],
                confidence,
            )
            if candidate is not None:
                candidates.append(candidate)
        for finding in report.key_findings:
            title = sanitize_completion_text(finding.get("title", "")).strip()
            if not title or contains_candidate_sensitive_text(title):
                continue
            candidate = self._candidate(
                report,
                LessonKind.GENERAL_INSIGHT,
                f"Preserve the evidence-backed finding '{title}' as reusable research context.",
                "A persisted finding can guide a later research question but is not a universal conclusion.",
                self._references(finding),
                [],
                0.64,
            )
            if candidate is not None:
                candidates.append(candidate)
        unique = {item.lesson_id: item for item in candidates}
        return list(unique.values())[: self.MAX_CANDIDATES]

    @staticmethod
    def write(path: str | Path, challenge_id: str, candidates: Iterable[LessonCandidate]) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(f"{output.suffix}.tmp")
        temporary.write_text(json.dumps({
            "schema_version": 1,
            "challenge_id": challenge_id,
            "candidates": [item.to_dict() for item in candidates],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)
        return output

    @staticmethod
    def _references(item: Mapping[str, Any]) -> list[str]:
        raw = item.get("artifact_refs", [])
        if not isinstance(raw, list):
            return []
        references: list[str] = []
        for reference in raw:
            if isinstance(reference, Mapping) and reference.get("artifact_id"):
                references.append(str(reference["artifact_id"]))
            elif isinstance(reference, str):
                references.append(reference)
        return list(dict.fromkeys(references))[:64]

    @staticmethod
    def _candidate(
        report: ChallengeReport,
        kind: LessonKind,
        statement: str,
        rationale: str,
        evidence_refs: Iterable[str],
        experiment_refs: Iterable[str],
        confidence: float,
    ) -> LessonCandidate | None:
        if contains_candidate_sensitive_text(statement) or contains_candidate_sensitive_text(rationale):
            return None
        evidence = tuple(dict.fromkeys(item for item in evidence_refs if item))[:64]
        experiments = tuple(dict.fromkeys(item for item in experiment_refs if item))[:32]
        key = f"{report.challenge_id}\0{kind.value}\0{statement}"
        return LessonCandidate(
            lesson_id="lesson-" + hashlib.sha256(key.encode()).hexdigest()[:12],
            kind=kind,
            statement=statement,
            rationale=rationale,
            source_challenge=report.challenge_id,
            evidence_refs=evidence,
            experiment_refs=experiments,
            confidence=confidence,
        )
