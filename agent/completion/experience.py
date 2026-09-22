"""Sanitized candidate extraction and explicit R8.6 review workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from agent.completion.models import (
    ChallengeReport,
    ExperienceCandidate,
    ExperienceReviewStatus,
    contains_candidate_sensitive_text,
)
from agent.experience.models import ExperienceRecord
from agent.experience.quality import ExperienceQualityStore
from agent.experience.store import DEFAULT_EXPERIENCE_PATH, ExperienceStore


class ExperienceCandidateExtractor:
    """Extract a small rule-driven candidate set; no LLM or automatic merge."""

    MAX_CANDIDATES = 5

    def extract(
        self,
        report: ChallengeReport,
        experiment_history: Iterable[Any] = (),
        lessons: Iterable[str] = (),
        lesson_candidates: Iterable[Any] = (),
    ) -> List[ExperienceCandidate]:
        signal = self._signal_text(report, experiment_history, lessons)
        if contains_candidate_sensitive_text(signal) or contains_candidate_sensitive_text(
            report.challenge_id
        ):
            return []

        rules = (
            (
                "sql_injection",
                ("sqlite", "sqlite_master"),
                "SQLite behavior requires catalog identification before query-shape selection.",
                "Confirm the database family, then use evidence-backed SQLite catalog enumeration.",
                "Identify the database family before selecting a query strategy.",
                0.90,
            ),
            (
                "sql_injection",
                ("sql", "database"),
                "Database-specific behavior should be identified before query-shape selection.",
                "Compare controlled responses and identify the database family before the next test.",
                "Separate database identification from later technique selection.",
                0.78,
            ),
            (
                "authentication",
                ("login", "authentication"),
                "Authentication behavior should be mapped before testing protected application paths.",
                "Record the observed state transition and compare access before and after authentication.",
                "Use evidence-backed state comparison when analyzing access control.",
                0.72,
            ),
            (
                "authorization_analysis",
                ("authorization", "access"),
                "Access-state behavior should be compared across evidence-backed application states.",
                "Record a bounded baseline for each permitted state before interpreting access differences.",
                "Keep authentication and authorization observations distinct.",
                0.76,
            ),
            (
                "parameter_behavior",
                ("parameter", "response"),
                "User-controlled input should be mapped to structural response behavior.",
                "Record input location and shape, then compare bounded response characteristics.",
                "Separate an observed response difference from its possible explanation.",
                0.74,
            ),
            (
                "file_processing",
                ("file", "processing"),
                "File-processing behavior should be characterized from accepted shapes and outcomes.",
                "Record local processing observations before choosing a deeper research question.",
                "Treat processing errors as evidence rather than a weakness verdict.",
                0.72,
            ),
            (
                "parser_behavior",
                ("parser", "error"),
                "Parser error structure can guide the next bounded comparison.",
                "Record format, structural keys, and error patterns before interpreting parser behavior.",
                "Preserve the distinction between a parser observation and a security conclusion.",
                0.75,
            ),
            (
                "business_logic",
                ("business", "state"),
                "Business inputs should be related to explicit application-state transitions.",
                "Compare permitted state before and after one bounded action.",
                "Use state evidence to avoid assumptions about application rules.",
                0.76,
            ),
            (
                "web_failed_experiment",
                ("web", "failed"),
                "A failed Web experiment is reusable evidence about an unsupported research path.",
                "Review the expected and actual structures before designing a different bounded experiment.",
                "Do not repeat a failed experiment without new discriminating evidence.",
                0.68,
            ),
            (
                "binary_analysis",
                ("binary", "symbol"),
                "Binary structure should be mapped before selecting a deeper analysis technique.",
                "Record format, architecture, and symbol evidence before planning the next experiment.",
                "Establish binary structure before technique selection.",
                0.72,
            ),
            (
                "crypto_pattern",
                ("cipher", "crypto"),
                "Cryptographic structure should be identified before choosing a solving strategy.",
                "Record observable format and repetition before testing a candidate construction.",
                "Separate structural identification from construction-specific analysis.",
                0.72,
            ),
        )
        candidates: List[ExperienceCandidate] = []
        source_evidence = self._source_evidence(report, lesson_candidates)
        successful = any(
            str(item.get("status", "")).upper() in {"SUCCESS", "COMPLETED"}
            for item in report.experiments
        )
        seen_categories: set[str] = set()
        for category, keywords, pattern, strategy, lesson, confidence in rules:
            if category in seen_categories or not all(keyword in signal for keyword in keywords):
                continue
            candidate = ExperienceCandidate(
                id=self._candidate_id(report.challenge_id, category, pattern),
                category=category,
                pattern=pattern,
                strategy=strategy,
                lesson=lesson,
                source_challenge=report.challenge_id,
                confidence=confidence,
                source_evidence=source_evidence,
                lesson_kind=(
                    "FAILED_STRATEGY"
                    if category == "web_failed_experiment"
                    else "SUCCESSFUL_STRATEGY"
                    if successful
                    else "GENERAL_INSIGHT"
                ),
            )
            candidates.append(candidate)
            seen_categories.add(category)
            if len(candidates) >= self.MAX_CANDIDATES:
                break
        return candidates

    @staticmethod
    def _source_evidence(
        report: ChallengeReport,
        lesson_candidates: Iterable[Any],
    ) -> tuple[str, ...]:
        references: list[str] = []
        for item in report.evidence:
            evidence_id = str(item.get("evidence_id", ""))
            if evidence_id:
                references.append(evidence_id)
            raw_refs = item.get("artifact_refs", [])
            if isinstance(raw_refs, list):
                references.extend(
                    str(ref.get("artifact_id"))
                    for ref in raw_refs
                    if isinstance(ref, Mapping) and ref.get("artifact_id")
                )
        for item in lesson_candidates:
            references.extend(str(value) for value in getattr(item, "evidence_refs", ()))
        return tuple(dict.fromkeys(item for item in references if item))[:64]

    @staticmethod
    def _candidate_id(challenge_id: str, category: str, pattern: str) -> str:
        digest = hashlib.sha256(
            f"{challenge_id}\0{category}\0{pattern}".encode("utf-8")
        ).hexdigest()[:12]
        return f"candidate-{digest}"

    @staticmethod
    def _signal_text(
        report: ChallengeReport,
        experiment_history: Iterable[Any],
        lessons: Iterable[str],
    ) -> str:
        values = [report.summary, report.domain]
        for item in report.key_findings:
            values.extend(str(item.get(key, "")) for key in ("title", "description"))
        for item in report.experiments:
            values.extend(
                str(item.get(key, ""))
                for key in ("goal", "expected_result", "actual_result", "status")
            )
        for item in report.evidence:
            values.extend(str(item.get(key, "")) for key in ("source", "observation"))
        for item in experiment_history:
            raw = _as_mapping(item)
            values.extend(
                str(raw.get(key, ""))
                for key in ("goal", "expected_result", "actual_result", "status")
            )
        values.extend(str(item) for item in lessons)
        return " ".join(values).lower()


class ExperienceCandidateStore:
    """Atomic per-challenge JSON storage for review candidates."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path, *, challenge_id: str | None = None) -> None:
        self.path = Path(path)
        self.challenge_id = challenge_id
        self._candidates: List[ExperienceCandidate] = []
        if self.path.is_file():
            self._load()

    def list(self) -> List[ExperienceCandidate]:
        return list(self._candidates)

    def get(self, candidate_id: str) -> ExperienceCandidate | None:
        return next((item for item in self._candidates if item.id == candidate_id), None)

    def replace_all(self, candidates: Iterable[ExperienceCandidate]) -> List[ExperienceCandidate]:
        records = list(candidates)
        ids = {item.id for item in records}
        if len(ids) != len(records):
            raise ValueError("duplicate experience candidate id")
        challenge_ids = {item.source_challenge for item in records}
        if self.challenge_id is None and len(challenge_ids) == 1:
            self.challenge_id = next(iter(challenge_ids))
        if self.challenge_id is None:
            raise ValueError("challenge_id is required for an empty candidate store")
        if any(item.source_challenge != self.challenge_id for item in records):
            raise ValueError("candidate belongs to a different challenge")
        self._candidates = records
        self._persist()
        return self.list()

    def merge_extracted(
        self,
        candidates: Iterable[ExperienceCandidate],
    ) -> List[ExperienceCandidate]:
        """Replace pending extraction while preserving completed review decisions."""

        previous = {item.id: item for item in self._candidates}
        merged: List[ExperienceCandidate] = []
        new_ids: set[str] = set()
        for item in candidates:
            old = previous.get(item.id)
            merged.append(
                replace(item, review_status=old.review_status) if old is not None else item
            )
            new_ids.add(item.id)
        merged.extend(
            item
            for item in previous.values()
            if item.id not in new_ids and item.review_status != ExperienceReviewStatus.PENDING
        )
        return self.replace_all(merged)

    def update_status(
        self,
        candidate_id: str,
        status: ExperienceReviewStatus,
    ) -> ExperienceCandidate:
        candidate = self.get(candidate_id)
        if candidate is None:
            raise ValueError(f"unknown experience candidate ID: {candidate_id}")
        if candidate.review_status == status:
            return candidate
        if candidate.review_status != ExperienceReviewStatus.PENDING:
            raise ValueError(
                f"candidate is already {candidate.review_status.value.lower()}"
            )
        updated = replace(candidate, review_status=status)
        self._candidates = [
            updated if item.id == candidate_id else item for item in self._candidates
        ]
        self._persist()
        return updated

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("candidate JSON must contain an object")
        if raw.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("unsupported candidate store schema version")
        challenge_id = raw.get("challenge_id")
        if not isinstance(challenge_id, str) or not challenge_id.strip():
            raise ValueError("candidate JSON requires challenge_id")
        if self.challenge_id is not None and challenge_id != self.challenge_id:
            raise ValueError("candidate store belongs to a different challenge")
        values = raw.get("candidates")
        if not isinstance(values, list) or not all(isinstance(item, Mapping) for item in values):
            raise ValueError("candidate JSON candidates must contain an array")
        self.challenge_id = challenge_id
        self._candidates = [ExperienceCandidate.from_dict(item) for item in values]
        if any(item.source_challenge != challenge_id for item in self._candidates):
            raise ValueError("candidate source challenge is inconsistent")

    def _persist(self) -> None:
        if self.challenge_id is None:
            raise ValueError("challenge_id is required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": self.SCHEMA_VERSION,
                    "challenge_id": self.challenge_id,
                    "candidates": [item.to_dict() for item in self._candidates],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)


class ExperienceCandidateCatalog:
    """Find and review candidates across challenge folders."""

    def __init__(
        self,
        challenge_root: str | Path = "experiences/challenges",
        global_store: str | Path = DEFAULT_EXPERIENCE_PATH,
        quality_store: str | Path | None = None,
    ) -> None:
        self.challenge_root = Path(challenge_root)
        self.global_store = Path(global_store)
        self.quality_store = (
            Path(quality_store)
            if quality_store is not None
            else self.global_store.with_name("experience-quality.json")
        )

    def list(self) -> List[ExperienceCandidate]:
        records: List[ExperienceCandidate] = []
        for path in self._paths():
            records.extend(ExperienceCandidateStore(path).list())
        return sorted(records, key=lambda item: (item.source_challenge, item.id))

    def approve(self, candidate_id: str) -> ExperienceCandidate:
        store, candidate = self._locate(candidate_id)
        if any(
            contains_candidate_sensitive_text(value)
            for value in (
                candidate.category,
                candidate.pattern,
                candidate.strategy,
                candidate.lesson,
                candidate.source_challenge,
            )
        ):
            raise ValueError("candidate contains prohibited challenge-sensitive terms")
        if candidate.review_status == ExperienceReviewStatus.REJECTED:
            raise ValueError("rejected candidate cannot be approved")
        if candidate.review_status == ExperienceReviewStatus.APPROVED:
            stored = ExperienceStore(self.global_store).add(self._to_experience(candidate))
            ExperienceQualityStore(self.quality_store).ensure(
                stored,
                source_challenge=candidate.source_challenge,
                source_evidence=candidate.source_evidence,
            )
            return candidate
        stored = ExperienceStore(self.global_store).add(self._to_experience(candidate))
        ExperienceQualityStore(self.quality_store).ensure(
            stored,
            source_challenge=candidate.source_challenge,
            source_evidence=candidate.source_evidence,
        )
        return store.update_status(candidate_id, ExperienceReviewStatus.APPROVED)

    def reject(self, candidate_id: str) -> ExperienceCandidate:
        store, candidate = self._locate(candidate_id)
        if candidate.review_status == ExperienceReviewStatus.APPROVED:
            raise ValueError("approved candidate cannot be rejected")
        return store.update_status(candidate_id, ExperienceReviewStatus.REJECTED)

    def _locate(
        self,
        candidate_id: str,
    ) -> tuple[ExperienceCandidateStore, ExperienceCandidate]:
        matches: list[tuple[ExperienceCandidateStore, ExperienceCandidate]] = []
        for path in self._paths():
            store = ExperienceCandidateStore(path)
            candidate = store.get(candidate_id)
            if candidate is not None:
                matches.append((store, candidate))
        if not matches:
            raise ValueError(f"unknown experience candidate ID: {candidate_id}")
        if len(matches) > 1:
            raise ValueError(f"ambiguous experience candidate ID: {candidate_id}")
        return matches[0]

    def _paths(self) -> List[Path]:
        if not self.challenge_root.exists():
            return []
        return sorted(self.challenge_root.glob("*/experience_candidates.json"))

    @staticmethod
    def _to_experience(candidate: ExperienceCandidate) -> ExperienceRecord:
        domain_by_category = {
            "sql_injection": "web",
            "authentication": "web",
            "authorization_analysis": "web",
            "parameter_behavior": "web",
            "file_processing": "web",
            "parser_behavior": "web",
            "business_logic": "web",
            "web_failed_experiment": "web",
            "binary_analysis": "reverse",
            "crypto_pattern": "crypto",
        }
        digest = hashlib.sha256(candidate.id.encode("utf-8")).hexdigest()[:12]
        return ExperienceRecord(
            id=f"experience-{digest}",
            domain=domain_by_category.get(candidate.category, "misc"),
            category=candidate.category,
            trigger=candidate.pattern,
            pattern=candidate.pattern,
            strategy=candidate.strategy,
            lesson=candidate.lesson,
            failure="Do not promote an unverified reusable pattern to a challenge-specific fact.",
            source_run=candidate.source_challenge,
            confidence=candidate.confidence,
        )


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    data = getattr(value, "__dict__", None)
    return dict(data) if isinstance(data, Mapping) else {}
