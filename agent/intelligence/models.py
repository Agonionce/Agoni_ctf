"""JSON-friendly domain models for R2 CTF intelligence."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Type, TypeVar


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CONFIRMED = "CONFIRMED"


class HypothesisStatus(str, Enum):
    OPEN = "OPEN"
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"
    CONFIRMED = "CONFIRMED"


class HypothesisSource(str, Enum):
    ANALYZER = "ANALYZER"
    INTELLIGENCE = "INTELLIGENCE"
    DOMAIN_RUNTIME = "DOMAIN_RUNTIME"
    EXPERIENCE = "EXPERIENCE"
    MANUAL = "MANUAL"


class OpenQuestionStatus(str, Enum):
    OPEN = "OPEN"
    ANSWERED = "ANSWERED"
    DISCARDED = "DISCARDED"


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CredentialStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    ACTIVE = "ACTIVE"
    INVALID = "INVALID"
    REVOKED = "REVOKED"


EnumT = TypeVar("EnumT", bound=Enum)


def enum_from(value: Any, enum_type: Type[EnumT], default: EnumT) -> EnumT:
    try:
        return enum_type(str(value))
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str
    relation_type: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactReference":
        return cls(
            artifact_id=str(data["artifact_id"]),
            relation_type=str(data.get("relation_type", "evidence_for")),
        )


def artifact_references(value: Any) -> List[ArtifactReference]:
    if not isinstance(value, list):
        return []
    references: List[ArtifactReference] = []
    for item in value:
        if isinstance(item, ArtifactReference):
            references.append(item)
        elif isinstance(item, Mapping) and item.get("artifact_id"):
            references.append(ArtifactReference.from_dict(item))
    return references


@dataclass
class Fact:
    category: str
    content: str
    confidence: Confidence = Confidence.MEDIUM
    source_step: int = 0
    artifact_refs: List[ArtifactReference] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("fact"))
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Fact":
        return cls(
            id=str(data.get("id") or new_id("fact")),
            category=str(data["category"]),
            content=str(data["content"]),
            confidence=enum_from(data.get("confidence"), Confidence, Confidence.MEDIUM),
            source_step=int(data.get("source_step", 0)),
            artifact_refs=artifact_references(data.get("artifact_refs")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class Hypothesis:
    statement: str
    status: HypothesisStatus = HypothesisStatus.OPEN
    confidence: Confidence | float = Confidence.LOW
    supporting_facts: List[str] = field(default_factory=list)
    contradicting_facts: List[str] = field(default_factory=list)
    domain: str = "misc"
    evidence_refs: List[str] = field(default_factory=list)
    source: HypothesisSource = HypothesisSource.MANUAL
    priority: Priority = Priority.MEDIUM
    related_artifacts: List[ArtifactReference] = field(default_factory=list)
    experience_influence: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("hypothesis"))
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not isinstance(self.statement, str) or not self.statement.strip():
            raise ValueError("statement must be a non-empty string")
        if not isinstance(self.domain, str) or not self.domain.strip():
            raise ValueError("domain must be a non-empty string")
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (Confidence, int, float)
        ):
            raise ValueError("confidence must be a Confidence or number in [0, 1]")
        if isinstance(self.confidence, (int, float)) and not 0 <= self.confidence <= 1:
            raise ValueError("numeric confidence must be in [0, 1]")
        if not isinstance(self.status, HypothesisStatus):
            raise ValueError("status must be a HypothesisStatus")
        if not isinstance(self.source, HypothesisSource):
            raise ValueError("source must be a HypothesisSource")
        if not isinstance(self.priority, Priority):
            raise ValueError("priority must be a Priority")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Hypothesis":
        raw_confidence = data.get("confidence")
        confidence: Confidence | float
        if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
            confidence = float(raw_confidence)
        else:
            confidence = enum_from(raw_confidence, Confidence, Confidence.LOW)
        return cls(
            id=str(data.get("id") or new_id("hypothesis")),
            statement=str(data["statement"]),
            status=enum_from(data.get("status"), HypothesisStatus, HypothesisStatus.OPEN),
            confidence=confidence,
            supporting_facts=_string_list(data.get("supporting_facts")),
            contradicting_facts=_string_list(data.get("contradicting_facts")),
            domain=str(data.get("domain") or "misc"),
            evidence_refs=_string_list(data.get("evidence_refs")),
            source=enum_from(
                data.get("source"),
                HypothesisSource,
                HypothesisSource.MANUAL,
            ),
            priority=enum_from(data.get("priority"), Priority, Priority.MEDIUM),
            related_artifacts=artifact_references(data.get("related_artifacts")),
            experience_influence=_string_list(data.get("experience_influence")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class FailedAttempt:
    category: str
    target: str
    method: str
    input_payload: str
    result: str
    reason: str
    source_step: int
    artifact_refs: List[ArtifactReference] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("attempt"))
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FailedAttempt":
        return cls(
            id=str(data.get("id") or new_id("attempt")),
            category=str(data["category"]),
            target=str(data.get("target", "")),
            method=str(data["method"]),
            input_payload=str(data.get("input_payload", "")),
            result=str(data.get("result", "failed")),
            reason=str(data.get("reason", "")),
            source_step=int(data.get("source_step", 0)),
            artifact_refs=artifact_references(data.get("artifact_refs")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class Finding:
    title: str
    description: str
    importance: Priority = Priority.MEDIUM
    related_facts: List[str] = field(default_factory=list)
    related_artifacts: List[ArtifactReference] = field(default_factory=list)
    source_steps: List[int] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("finding"))
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Finding":
        source_steps = data.get("source_steps", [])
        return cls(
            id=str(data.get("id") or new_id("finding")),
            title=str(data["title"]),
            description=str(data["description"]),
            importance=enum_from(data.get("importance"), Priority, Priority.MEDIUM),
            related_facts=_string_list(data.get("related_facts")),
            related_artifacts=artifact_references(data.get("related_artifacts")),
            source_steps=[int(step) for step in source_steps] if isinstance(source_steps, list) else [],
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class Credential:
    credential_type: str
    value: str
    location: str
    status: CredentialStatus = CredentialStatus.UNKNOWN
    source: str = ""
    id: str = field(default_factory=lambda: new_id("credential"))
    created_at: str = field(default_factory=utc_now_iso)

    def masked_value(self) -> str:
        if len(self.value) <= 4:
            return "*" * len(self.value)
        return f"{self.value[:4]}{'*' * min(8, len(self.value) - 4)}"

    def safe_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["value"] = self.masked_value()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Credential":
        return cls(
            id=str(data.get("id") or new_id("credential")),
            credential_type=str(data.get("credential_type", data.get("type", "unknown"))),
            value=str(data["value"]),
            location=str(data.get("location", "")),
            status=enum_from(data.get("status"), CredentialStatus, CredentialStatus.UNKNOWN),
            source=str(data.get("source", "")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class AttackSurface:
    category: str
    target: str
    method: str = ""
    parameters: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    source_step: int = 0
    artifact_refs: List[ArtifactReference] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("surface"))
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AttackSurface":
        details = data.get("details", {})
        return cls(
            id=str(data.get("id") or new_id("surface")),
            category=str(data["category"]),
            target=str(data["target"]),
            method=str(data.get("method", "")),
            parameters=_string_list(data.get("parameters")),
            details=dict(details) if isinstance(details, Mapping) else {},
            source_step=int(data.get("source_step", 0)),
            artifact_refs=artifact_references(data.get("artifact_refs")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class EndpointFinding:
    """One evidence-backed Web endpoint observation for the current challenge."""

    path: str
    method: str = "GET"
    parameters: List[str] = field(default_factory=list)
    source: str = "unknown"
    confidence: Confidence = Confidence.MEDIUM
    source_step: int = 0
    artifact_refs: List[ArtifactReference] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("endpoint"))
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            raise ValueError("endpoint path must be an origin-relative path")
        self.method = self.method.upper()
        self.parameters = sorted(set(self.parameters))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EndpointFinding":
        return cls(
            id=str(data.get("id") or new_id("endpoint")),
            path=str(data["path"]),
            method=str(data.get("method", "GET")),
            parameters=_string_list(data.get("parameters")),
            source=str(data.get("source", "unknown")),
            confidence=enum_from(
                data.get("confidence"), Confidence, Confidence.MEDIUM
            ),
            source_step=int(data.get("source_step", 0)),
            artifact_refs=artifact_references(data.get("artifact_refs")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class OpenQuestion:
    question: str
    priority: Priority = Priority.MEDIUM
    status: OpenQuestionStatus = OpenQuestionStatus.OPEN
    related_findings: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("question"))
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OpenQuestion":
        return cls(
            id=str(data.get("id") or new_id("question")),
            question=str(data["question"]),
            priority=enum_from(data.get("priority"), Priority, Priority.MEDIUM),
            status=enum_from(data.get("status"), OpenQuestionStatus, OpenQuestionStatus.OPEN),
            related_findings=_string_list(data.get("related_findings")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass(frozen=True)
class ArtifactLink:
    artifact_id: str
    relation_type: str
    entity_type: str
    entity_id: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactLink":
        return cls(
            artifact_id=str(data["artifact_id"]),
            relation_type=str(data["relation_type"]),
            entity_type=str(data["entity_type"]),
            entity_id=str(data["entity_id"]),
        )


@dataclass
class IntelligenceState:
    challenge_id: str
    facts: List[Fact] = field(default_factory=list)
    hypotheses: List[Hypothesis] = field(default_factory=list)
    failed_attempts: List[FailedAttempt] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    credentials: List[Credential] = field(default_factory=list)
    attack_surface: List[AttackSurface] = field(default_factory=list)
    endpoint_findings: List[EndpointFinding] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)
    experiments: List["Experiment"] = field(default_factory=list)
    evidence: List["EvidenceRecord"] = field(default_factory=list)
    artifact_links: List[ArtifactLink] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self, *, mask_credentials: bool = False) -> Dict[str, Any]:
        data = asdict(self)
        if mask_credentials:
            data["credentials"] = [credential.safe_dict() for credential in self.credentials]
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "IntelligenceState":
        from agent.intelligence.experiment.models import EvidenceRecord, Experiment

        return cls(
            challenge_id=str(data["challenge_id"]),
            facts=[Fact.from_dict(item) for item in _mappings(data.get("facts"))],
            hypotheses=[Hypothesis.from_dict(item) for item in _mappings(data.get("hypotheses"))],
            failed_attempts=[
                FailedAttempt.from_dict(item) for item in _mappings(data.get("failed_attempts"))
            ],
            findings=[Finding.from_dict(item) for item in _mappings(data.get("findings"))],
            credentials=[Credential.from_dict(item) for item in _mappings(data.get("credentials"))],
            attack_surface=[
                AttackSurface.from_dict(item) for item in _mappings(data.get("attack_surface"))
            ],
            endpoint_findings=[
                EndpointFinding.from_dict(item)
                for item in _mappings(data.get("endpoint_findings"))
            ],
            open_questions=[
                OpenQuestion.from_dict(item) for item in _mappings(data.get("open_questions"))
            ],
            experiments=[
                Experiment.from_dict(item) for item in _mappings(data.get("experiments"))
            ],
            evidence=[
                EvidenceRecord.from_dict(item) for item in _mappings(data.get("evidence"))
            ],
            artifact_links=[ArtifactLink.from_dict(item) for item in _mappings(data.get("artifact_links"))],
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )


def _mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


@dataclass(frozen=True)
class KnowledgeUpdateSuggestion:
    """Analyzer-proposed state mutation consumed only by KnowledgeUpdater."""

    kind: str
    payload: Dict[str, Any]
    operation: str = "add"
    source_step: int | None = None
    artifact_refs: List[ArtifactReference] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeUpdateSuggestion":
        kind = data.get("kind")
        payload = data.get("payload")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("knowledge update kind must be a non-empty string")
        if not isinstance(payload, Mapping):
            raise ValueError("knowledge update payload must be an object")
        operation = str(data.get("operation", "add"))
        if operation not in {"add", "update"}:
            raise ValueError("knowledge update operation must be add or update")
        raw_step = data.get("source_step")
        source_step = int(raw_step) if raw_step is not None else None
        return cls(
            kind=kind,
            payload=dict(payload),
            operation=operation,
            source_step=source_step,
            artifact_refs=artifact_references(data.get("artifact_refs")),
        )
