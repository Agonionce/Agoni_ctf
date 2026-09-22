"""Typed and sanitized R7 reusable experience records."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping


class ExperienceSecurityError(ValueError):
    """Raised when a record appears to contain target-specific private data."""


_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\b[A-Za-z][A-Za-z0-9_-]{1,31}\{[^}\r\n]+\}"),
    re.compile(r"(?i)\bsk-[a-z0-9_-]{8,}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|password|passwd|token|secret|credential)\s*[:=]\s*\S+"
    ),
    re.compile(r"(?i)\b(?:https?|ftp)://\S+"),
    re.compile(r"(?<![A-Za-z0-9])(?:\d{1,3}\.){3}\d{1,3}(?![A-Za-z0-9])"),
    re.compile(
        r"(?i)\b(?:authorization|proxy-authorization|x-api-key|api[_-]?key|"
        r"x-session|x-[a-z0-9-]{2,})\b\s*(?::|=|\bis\b)\s*"
        r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
    ),
    re.compile(
        r"(?<![A-Za-z0-9_./])/(?!/)[^\s`),;]+|"
        r"\b[A-Za-z]:\\[^\s`),;]+|"
        r"(?<!\\)\\\\[^\\\s]+\\[^\s`),;]+"
    ),
    re.compile(
        r"(?i)\b(?:planner(?:\s+reasoning)?|toolruntime|policyengine|"
        r"approvalmanager|agentruntime|[a-z][a-z0-9_]*tool)\b"
    ),
    re.compile(r"(?i)\b(?:headers?|payload|arguments?)\b\s*[:=]\s*[^\s,;]+"),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_experience_id() -> str:
    return f"experience-{uuid.uuid4().hex[:12]}"


def _require_text(value: object, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(normalized) > 1000:
        raise ValueError(f"{field_name} exceeds the experience size limit")
    return normalized


def _reject_sensitive(value: str, field_name: str) -> None:
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(value):
            raise ExperienceSecurityError(
                f"{field_name} contains target-specific or sensitive data"
            )


@dataclass(frozen=True)
class ExperienceRecord:
    """A generic, reusable lesson extracted from one completed run."""

    domain: str
    category: str
    trigger: str
    pattern: str
    strategy: str
    lesson: str
    failure: str
    source_run: str
    confidence: float
    id: str = field(default_factory=new_experience_id)
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        text_fields = (
            "id",
            "domain",
            "category",
            "trigger",
            "pattern",
            "strategy",
            "lesson",
            "failure",
            "source_run",
            "created_at",
        )
        for field_name in text_fields:
            normalized = _require_text(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, normalized)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.domain):
            raise ValueError("domain must be a normalized identifier")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.category):
            raise ValueError("category must be a normalized identifier")
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", self.id):
            raise ValueError("id must be an opaque normalized identifier")
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", self.source_run):
            raise ExperienceSecurityError("source_run must be an opaque run identifier")
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ):
            raise ValueError("confidence must be a number in [0, 1]")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be a number in [0, 1]")
        object.__setattr__(self, "confidence", float(self.confidence))
        for field_name in (
            "trigger",
            "pattern",
            "strategy",
            "lesson",
            "failure",
        ):
            _reject_sensitive(getattr(self, field_name), field_name)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExperienceRecord":
        return cls(
            id=str(data.get("id") or new_experience_id()),
            domain=str(data["domain"]),
            category=str(data["category"]),
            trigger=str(data["trigger"]),
            pattern=str(data["pattern"]),
            strategy=str(data["strategy"]),
            lesson=str(data["lesson"]),
            failure=str(data["failure"]),
            source_run=str(data["source_run"]),
            confidence=float(data["confidence"]),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )
