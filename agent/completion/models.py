"""Typed models for R8.6 challenge completion outputs."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping, Sequence


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_candidate_id() -> str:
    return f"candidate-{uuid.uuid4().hex[:12]}"


def _require_text(value: object, field_name: str, *, max_length: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} exceeds the size limit")
    return normalized


def _mapping_tuple(value: Sequence[Mapping[str, Any]]) -> tuple[Dict[str, Any], ...]:
    return tuple(dict(item) for item in value)


class ExperienceReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


_CANDIDATE_SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(?:password|passwd|token|cookie|secret|flag|credential)s?\b"
)
_CANDIDATE_FLAG_VALUE_PATTERN = re.compile(
    r"(?i)\b[A-Za-z][A-Za-z0-9_-]{1,31}\{[^}\r\n]+\}"
)
_CANDIDATE_LABELED_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:authorization|proxy-authorization|x-api-key|api[_-]?key|"
    r"x-session|x-[a-z0-9-]{2,})\b\s*(?::|=|\bis\b)\s*"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
_CANDIDATE_AUTH_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{6,}|\bsk-[A-Za-z0-9_-]{12,}"
)
_CANDIDATE_ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./])/(?!/)[^\s`),;]+|"
    r"\b[A-Za-z]:\\[^\s`),;]+|"
    r"(?<!\\)\\\\[^\\\s]+\\[^\s`),;]+"
)
_CANDIDATE_INTERNAL_MARKER_PATTERN = re.compile(
    r"(?i)\b(?:planner(?:\s+reasoning)?|toolruntime|policyengine|"
    r"approvalmanager|agentruntime|[a-z][a-z0-9_]*tool)\b"
)
_CANDIDATE_INTERNAL_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:headers?|payload|arguments?)\b\s*[:=]\s*[^\s,;]+"
)


def contains_candidate_sensitive_text(value: str) -> bool:
    """Return true when reusable memory would retain prohibited secret classes."""

    return any(
        pattern.search(value)
        for pattern in (
            _CANDIDATE_SENSITIVE_PATTERN,
            _CANDIDATE_FLAG_VALUE_PATTERN,
            _CANDIDATE_LABELED_VALUE_PATTERN,
            _CANDIDATE_AUTH_VALUE_PATTERN,
            _CANDIDATE_ABSOLUTE_PATH_PATTERN,
            _CANDIDATE_INTERNAL_MARKER_PATTERN,
            _CANDIDATE_INTERNAL_VALUE_PATTERN,
        )
    )


@dataclass(frozen=True)
class ChallengeReport:
    """Read-only consolidation of one completed challenge run."""

    challenge_id: str
    summary: str
    domain: str
    status: str
    key_findings: tuple[Dict[str, Any], ...]
    experiments: tuple[Dict[str, Any], ...]
    artifacts: tuple[Dict[str, Any], ...]
    generated_at: str = field(default_factory=utc_now_iso)
    evidence: tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    flag_verification: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("challenge_id", "summary", "domain", "status", "generated_at"):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name),
            )
        for field_name in ("key_findings", "experiments", "artifacts", "evidence"):
            value = getattr(self, field_name)
            if (
                not isinstance(value, Sequence)
                or isinstance(value, (str, bytes))
                or not all(isinstance(item, Mapping) for item in value)
            ):
                raise ValueError(f"{field_name} must be an array of objects")
            object.__setattr__(self, field_name, _mapping_tuple(value))
        if not isinstance(self.flag_verification, Mapping):
            raise ValueError("flag_verification must be an object")
        object.__setattr__(self, "flag_verification", dict(self.flag_verification))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChallengeReport":
        return cls(
            challenge_id=str(data["challenge_id"]),
            summary=str(data["summary"]),
            domain=str(data["domain"]),
            status=str(data["status"]),
            key_findings=_read_mapping_tuple(data.get("key_findings")),
            experiments=_read_mapping_tuple(data.get("experiments")),
            artifacts=_read_mapping_tuple(data.get("artifacts")),
            generated_at=str(data.get("generated_at") or utc_now_iso()),
            evidence=_read_mapping_tuple(data.get("evidence")),
            flag_verification=(
                dict(data.get("flag_verification", {}))
                if isinstance(data.get("flag_verification", {}), Mapping)
                else {}
            ),
        )


@dataclass(frozen=True)
class ExperienceCandidate:
    """A sanitized reusable lesson that requires explicit human review."""

    category: str
    pattern: str
    strategy: str
    lesson: str
    source_challenge: str
    confidence: float
    id: str = field(default_factory=new_candidate_id)
    review_status: ExperienceReviewStatus = ExperienceReviewStatus.PENDING
    source_evidence: tuple[str, ...] = field(default_factory=tuple)
    lesson_kind: str = "GENERAL_INSIGHT"

    def __post_init__(self) -> None:
        for field_name in (
            "id",
            "category",
            "pattern",
            "strategy",
            "lesson",
            "source_challenge",
        ):
            normalized = _require_text(getattr(self, field_name), field_name, max_length=1000)
            object.__setattr__(self, field_name, normalized)
        if re.fullmatch(r"[A-Za-z0-9._:-]+", self.id) is None:
            raise ValueError("id must be an opaque normalized identifier")
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.category) is None:
            raise ValueError("category must be a normalized identifier")
        if re.fullmatch(r"[A-Za-z0-9._:-]+", self.source_challenge) is None:
            raise ValueError("source_challenge must be an opaque identifier")
        if not isinstance(self.review_status, ExperienceReviewStatus):
            raise ValueError("review_status must be an ExperienceReviewStatus")
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ):
            raise ValueError("confidence must be a number in [0, 1]")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be a number in [0, 1]")
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(
            self,
            "source_evidence",
            tuple(dict.fromkeys(str(item) for item in self.source_evidence if str(item).strip()))[:64],
        )
        if any(
            re.fullmatch(r"[A-Za-z0-9._:-]+", item) is None
            for item in self.source_evidence
        ):
            raise ValueError("source_evidence must contain opaque identifiers")
        if self.lesson_kind not in {
            "SUCCESSFUL_STRATEGY", "FAILED_STRATEGY", "GENERAL_INSIGHT"
        }:
            raise ValueError("lesson_kind is invalid")
        for field_name in (
            "category",
            "pattern",
            "strategy",
            "lesson",
            "source_challenge",
        ):
            if contains_candidate_sensitive_text(getattr(self, field_name)):
                raise ValueError(
                    f"{field_name} contains prohibited challenge-sensitive terms"
                )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["review_status"] = self.review_status.value
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExperienceCandidate":
        try:
            review_status = ExperienceReviewStatus(
                str(data.get("review_status", ExperienceReviewStatus.PENDING.value))
            )
        except ValueError as error:
            raise ValueError("unknown experience candidate review status") from error
        return cls(
            id=str(data.get("id") or new_candidate_id()),
            category=str(data["category"]),
            pattern=str(data["pattern"]),
            strategy=str(data["strategy"]),
            lesson=str(data["lesson"]),
            source_challenge=str(data["source_challenge"]),
            confidence=float(data["confidence"]),
            review_status=review_status,
            source_evidence=(
                tuple(str(item) for item in data.get("source_evidence", []))
                if isinstance(data.get("source_evidence"), list)
                else ()
            ),
            lesson_kind=str(data.get("lesson_kind", "GENERAL_INSIGHT")),
        )


def _read_mapping_tuple(value: object) -> tuple[Dict[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("report collections must be arrays")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError("report collections must contain objects")
    return tuple(dict(item) for item in value)
