"""Typed, JSON-safe models for the R8 Web Intelligence Layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from agent.intelligence.models import EndpointFinding


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


@dataclass(frozen=True)
class HTMLForm:
    action: str
    method: str
    inputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["inputs"] = list(self.inputs)
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HTMLForm":
        raw_inputs = data.get("inputs", [])
        return cls(
            action=str(data.get("action", "/")),
            method=str(data.get("method", "GET")).upper(),
            inputs=(
                tuple(str(item) for item in raw_inputs)
                if isinstance(raw_inputs, list)
                else ()
            ),
        )


@dataclass(frozen=True)
class ClientRequestContract:
    """A literal, same-origin request shape found in captured client code.

    This is passive evidence only.  It records a browser client's declared
    request contract without evaluating JavaScript, following redirects, or
    creating a request on its own.
    """

    method: str
    path: str
    query: tuple[tuple[str, str], ...] = ()
    json_body: tuple[tuple[str, str], ...] = ()
    header_names: tuple[str, ...] = ()
    source: str = "inline client code"

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "query": [list(item) for item in self.query],
            "json_body": [list(item) for item in self.json_body],
            "header_names": list(self.header_names),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClientRequestContract":
        return cls(
            method=str(data.get("method", "GET")).upper(),
            path=str(data.get("path", "/")),
            query=_pairs(data.get("query")),
            json_body=_pairs(data.get("json_body")),
            header_names=(
                tuple(str(item) for item in data.get("header_names", []))
                if isinstance(data.get("header_names"), list)
                else ()
            ),
            source=str(data.get("source", "inline client code")),
        )


@dataclass(frozen=True)
class HTMLAnalysis:
    request_id: str
    url: str
    title: str | None = None
    forms: tuple[HTMLForm, ...] = ()
    links: tuple[str, ...] = ()
    scripts: tuple[str, ...] = ()
    comments: tuple[str, ...] = ()
    client_requests: tuple[ClientRequestContract, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "url": self.url,
            "title": self.title,
            "forms": [item.to_dict() for item in self.forms],
            "links": list(self.links),
            "scripts": list(self.scripts),
            "comments": list(self.comments),
            "client_requests": [item.to_dict() for item in self.client_requests],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HTMLAnalysis":
        return cls(
            request_id=str(data.get("request_id", "")),
            url=str(data.get("url", "")),
            title=(str(data["title"]) if data.get("title") is not None else None),
            forms=tuple(
                HTMLForm.from_dict(item) for item in _mapping_list(data.get("forms"))
            ),
            links=tuple(str(item) for item in data.get("links", []))
            if isinstance(data.get("links"), list)
            else (),
            scripts=tuple(str(item) for item in data.get("scripts", []))
            if isinstance(data.get("scripts"), list)
            else (),
            comments=tuple(str(item) for item in data.get("comments", []))
            if isinstance(data.get("comments"), list)
            else (),
            client_requests=tuple(
                ClientRequestContract.from_dict(item)
                for item in _mapping_list(data.get("client_requests"))
            ),
        )


@dataclass(frozen=True)
class TechnologyEvidence:
    technology: str
    evidence: str
    source: str
    confidence: str = "MEDIUM"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TechnologyEvidence":
        return cls(
            technology=str(data["technology"]),
            evidence=str(data.get("evidence", "")),
            source=str(data.get("source", "unknown")),
            confidence=str(data.get("confidence", "MEDIUM")),
        )


@dataclass(frozen=True)
class ResponseDifference:
    baseline_request_id: str
    current_request_id: str
    status_changed: bool
    baseline_status: int | None
    current_status: int | None
    length_difference: int
    title_changed: bool
    baseline_title: str | None
    current_title: str | None
    baseline_errors: tuple[str, ...] = ()
    current_errors: tuple[str, ...] = ()
    content_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["baseline_errors"] = list(self.baseline_errors)
        payload["current_errors"] = list(self.current_errors)
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResponseDifference":
        baseline_errors = data.get("baseline_errors", [])
        current_errors = data.get("current_errors", [])
        return cls(
            baseline_request_id=str(data.get("baseline_request_id", "")),
            current_request_id=str(data.get("current_request_id", "")),
            status_changed=bool(data.get("status_changed", False)),
            baseline_status=(
                int(data["baseline_status"])
                if isinstance(data.get("baseline_status"), int)
                else None
            ),
            current_status=(
                int(data["current_status"])
                if isinstance(data.get("current_status"), int)
                else None
            ),
            length_difference=int(data.get("length_difference", 0)),
            title_changed=bool(data.get("title_changed", False)),
            baseline_title=(
                str(data["baseline_title"])
                if data.get("baseline_title") is not None
                else None
            ),
            current_title=(
                str(data["current_title"])
                if data.get("current_title") is not None
                else None
            ),
            baseline_errors=(
                tuple(str(item) for item in baseline_errors)
                if isinstance(baseline_errors, list)
                else ()
            ),
            current_errors=(
                tuple(str(item) for item in current_errors)
                if isinstance(current_errors, list)
                else ()
            ),
            content_changed=bool(data.get("content_changed", False)),
        )


@dataclass(frozen=True)
class BehaviorFinding:
    title: str
    description: str
    response_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "response_ids": list(self.response_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BehaviorFinding":
        raw_ids = data.get("response_ids", [])
        return cls(
            title=str(data["title"]),
            description=str(data.get("description", "")),
            response_ids=(
                tuple(str(item) for item in raw_ids)
                if isinstance(raw_ids, list)
                else ()
            ),
        )


@dataclass(frozen=True)
class HypothesisProposal:
    statement: str
    domain: str = "web"
    confidence: float = 0.4
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "domain": self.domain,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisProposal":
        raw_evidence = data.get("evidence", [])
        return cls(
            statement=str(data["statement"]),
            domain=str(data.get("domain", "web")),
            confidence=float(data.get("confidence", 0.4)),
            evidence=(
                tuple(str(item) for item in raw_evidence)
                if isinstance(raw_evidence, list)
                else ()
            ),
        )


@dataclass(frozen=True)
class WebResponseProfile:
    """Bounded semantic description of one already captured response."""

    request_id: str
    url: str
    status_code: int | None
    content_type: str
    response_format: str
    body_length: int
    json_keys: tuple[str, ...] = ()
    error_patterns: tuple[str, ...] = ()
    state_markers: tuple[str, ...] = ()
    html_form_count: int = 0
    html_link_count: int = 0
    parameter_names: tuple[str, ...] = ()
    parameter_locations: tuple[tuple[str, str], ...] = ()
    parameter_shapes: tuple[tuple[str, str], ...] = ()
    body_sha256: str = ""
    body_complete: bool = True
    flag_candidates: tuple[str, ...] = ()
    content_signals: tuple[str, ...] = ()
    client_requests: tuple[ClientRequestContract, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "url": self.url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "response_format": self.response_format,
            "body_length": self.body_length,
            "json_keys": list(self.json_keys),
            "error_patterns": list(self.error_patterns),
            "state_markers": list(self.state_markers),
            "html_form_count": self.html_form_count,
            "html_link_count": self.html_link_count,
            "parameter_names": list(self.parameter_names),
            "parameter_locations": [list(item) for item in self.parameter_locations],
            "parameter_shapes": [list(item) for item in self.parameter_shapes],
            "body_sha256": self.body_sha256,
            "body_complete": self.body_complete,
            "flag_candidates": list(self.flag_candidates),
            "content_signals": list(self.content_signals),
            "client_requests": [item.to_dict() for item in self.client_requests],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebResponseProfile":
        return cls(
            request_id=str(data.get("request_id", "")),
            url=str(data.get("url", "")),
            status_code=(
                int(data["status_code"])
                if isinstance(data.get("status_code"), int)
                and not isinstance(data.get("status_code"), bool)
                else None
            ),
            content_type=str(data.get("content_type", "")),
            response_format=str(data.get("response_format", "TEXT")),
            body_length=int(data.get("body_length", 0)),
            json_keys=tuple(str(item) for item in data.get("json_keys", []))
            if isinstance(data.get("json_keys"), list) else (),
            error_patterns=tuple(str(item) for item in data.get("error_patterns", []))
            if isinstance(data.get("error_patterns"), list) else (),
            state_markers=tuple(str(item) for item in data.get("state_markers", []))
            if isinstance(data.get("state_markers"), list) else (),
            html_form_count=int(data.get("html_form_count", 0)),
            html_link_count=int(data.get("html_link_count", 0)),
            parameter_names=tuple(str(item) for item in data.get("parameter_names", []))
            if isinstance(data.get("parameter_names"), list) else (),
            parameter_locations=_pairs(data.get("parameter_locations")),
            parameter_shapes=_pairs(data.get("parameter_shapes")),
            body_sha256=str(data.get("body_sha256", "")),
            body_complete=bool(data.get("body_complete", True)),
            flag_candidates=tuple(str(item) for item in data.get("flag_candidates", []))
            if isinstance(data.get("flag_candidates"), list) else (),
            content_signals=tuple(str(item) for item in data.get("content_signals", []))
            if isinstance(data.get("content_signals"), list) else (),
            client_requests=tuple(
                ClientRequestContract.from_dict(item)
                for item in _mapping_list(data.get("client_requests"))
            ),
        )


@dataclass(frozen=True)
class WebStateDifference:
    """Structural difference between two response profiles."""

    baseline_request_id: str
    current_request_id: str
    status_changed: bool
    format_changed: bool
    json_keys_added: tuple[str, ...] = ()
    json_keys_removed: tuple[str, ...] = ()
    errors_added: tuple[str, ...] = ()
    errors_removed: tuple[str, ...] = ()
    state_markers_added: tuple[str, ...] = ()
    state_markers_removed: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return any((
            self.status_changed,
            self.format_changed,
            self.json_keys_added,
            self.json_keys_removed,
            self.errors_added,
            self.errors_removed,
            self.state_markers_added,
            self.state_markers_removed,
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_request_id": self.baseline_request_id,
            "current_request_id": self.current_request_id,
            "status_changed": self.status_changed,
            "format_changed": self.format_changed,
            "json_keys_added": list(self.json_keys_added),
            "json_keys_removed": list(self.json_keys_removed),
            "errors_added": list(self.errors_added),
            "errors_removed": list(self.errors_removed),
            "state_markers_added": list(self.state_markers_added),
            "state_markers_removed": list(self.state_markers_removed),
            "changed": self.changed,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebStateDifference":
        def values(name: str) -> tuple[str, ...]:
            raw = data.get(name, [])
            return tuple(str(item) for item in raw) if isinstance(raw, list) else ()
        return cls(
            baseline_request_id=str(data.get("baseline_request_id", "")),
            current_request_id=str(data.get("current_request_id", "")),
            status_changed=bool(data.get("status_changed", False)),
            format_changed=bool(data.get("format_changed", False)),
            json_keys_added=values("json_keys_added"),
            json_keys_removed=values("json_keys_removed"),
            errors_added=values("errors_added"),
            errors_removed=values("errors_removed"),
            state_markers_added=values("state_markers_added"),
            state_markers_removed=values("state_markers_removed"),
        )


@dataclass
class WebAttackSurface:
    endpoints: list[EndpointFinding] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)

    def normalize(self) -> None:
        self.endpoints.sort(key=lambda item: (item.path, item.method))
        self.parameters = sorted(set(self.parameters))
        self.technologies = sorted(set(self.technologies))

    def to_dict(self, *, endpoint_limit: int | None = None) -> dict[str, Any]:
        self.normalize()
        endpoints = self.endpoints
        if endpoint_limit is not None:
            endpoints = endpoints[:endpoint_limit]
        return {
            "endpoints": [
                {
                    "id": item.id,
                    "path": item.path,
                    "method": item.method,
                    "parameters": list(item.parameters),
                    "source": item.source,
                    "confidence": item.confidence.value,
                    "source_step": item.source_step,
                    "artifact_refs": [asdict(ref) for ref in item.artifact_refs],
                    "created_at": item.created_at,
                }
                for item in endpoints
            ],
            "parameters": list(self.parameters),
            "technologies": list(self.technologies),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebAttackSurface":
        raw_parameters = data.get("parameters", [])
        raw_technologies = data.get("technologies", [])
        surface = cls(
            endpoints=[
                EndpointFinding.from_dict(item)
                for item in _mapping_list(data.get("endpoints"))
            ],
            parameters=(
                [str(item) for item in raw_parameters]
                if isinstance(raw_parameters, list)
                else []
            ),
            technologies=(
                [str(item) for item in raw_technologies]
                if isinstance(raw_technologies, list)
                else []
            ),
        )
        surface.normalize()
        return surface


@dataclass
class WebIntelligenceState:
    html_analyses: list[HTMLAnalysis] = field(default_factory=list)
    attack_surface: WebAttackSurface = field(default_factory=WebAttackSurface)
    technology_evidence: list[TechnologyEvidence] = field(default_factory=list)
    response_differences: list[ResponseDifference] = field(default_factory=list)
    behavior_findings: list[BehaviorFinding] = field(default_factory=list)
    hypothesis_proposals: list[HypothesisProposal] = field(default_factory=list)
    response_profiles: list[WebResponseProfile] = field(default_factory=list)
    state_differences: list[WebStateDifference] = field(default_factory=list)

    def merge(self, other: "WebIntelligenceState") -> None:
        """Accumulate new passive evidence without discarding prior responses."""

        analyses = {item.request_id: item for item in self.html_analyses}
        analyses.update({item.request_id: item for item in other.html_analyses})
        self.html_analyses = list(analyses.values())

        endpoints = {
            (item.path, item.method): item for item in self.attack_surface.endpoints
        }
        confidence_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CONFIRMED": 3}
        for candidate in other.attack_surface.endpoints:
            identity = (candidate.path, candidate.method)
            existing = endpoints.get(identity)
            if existing is None:
                endpoints[identity] = candidate
                continue
            existing.parameters = sorted(
                {*existing.parameters, *candidate.parameters}
            )
            existing.source = ", ".join(
                sorted(
                    {
                        source.strip()
                        for source in [
                            *existing.source.split(","),
                            *candidate.source.split(","),
                        ]
                        if source.strip()
                    }
                )
            )
            if (
                confidence_order[candidate.confidence.value]
                > confidence_order[existing.confidence.value]
            ):
                existing.confidence = candidate.confidence
        self.attack_surface.endpoints = list(endpoints.values())
        self.attack_surface.parameters = sorted(
            {
                *self.attack_surface.parameters,
                *other.attack_surface.parameters,
            }
        )
        self.attack_surface.technologies = sorted(
            {
                *self.attack_surface.technologies,
                *other.attack_surface.technologies,
            }
        )
        technology = {
            (item.technology, item.evidence, item.source): item
            for item in [*self.technology_evidence, *other.technology_evidence]
        }
        self.technology_evidence = list(technology.values())
        differences = {
            (item.baseline_request_id, item.current_request_id): item
            for item in [*self.response_differences, *other.response_differences]
        }
        self.response_differences = list(differences.values())
        findings = {
            (item.title, item.response_ids): item
            for item in [*self.behavior_findings, *other.behavior_findings]
        }
        self.behavior_findings = list(findings.values())
        hypotheses = {
            item.statement: item
            for item in [*self.hypothesis_proposals, *other.hypothesis_proposals]
        }
        self.hypothesis_proposals = list(hypotheses.values())
        profiles = {
            item.request_id: item
            for item in [*self.response_profiles, *other.response_profiles]
        }
        self.response_profiles = list(profiles.values())
        state_differences = {
            (item.baseline_request_id, item.current_request_id): item
            for item in [*self.state_differences, *other.state_differences]
        }
        self.state_differences = list(state_differences.values())
        self.attack_surface.normalize()

    def to_dict(self) -> dict[str, Any]:
        return {
            "html_analyses": [item.to_dict() for item in self.html_analyses],
            "attack_surface": self.attack_surface.to_dict(),
            "technology_evidence": [
                item.to_dict() for item in self.technology_evidence
            ],
            "response_differences": [
                item.to_dict() for item in self.response_differences
            ],
            "behavior_findings": [item.to_dict() for item in self.behavior_findings],
            "hypothesis_proposals": [
                item.to_dict() for item in self.hypothesis_proposals
            ],
            "response_profiles": [
                item.to_dict() for item in self.response_profiles
            ],
            "state_differences": [
                item.to_dict() for item in self.state_differences
            ],
        }

    def artifact_payloads(self) -> dict[str, dict[str, Any]]:
        return {
            "html-analysis.json": {
                "analyses": [item.to_dict() for item in self.html_analyses]
            },
            "endpoint-map.json": self.attack_surface.to_dict(),
            "technology.json": {
                "evidence": [item.to_dict() for item in self.technology_evidence]
            },
            "response-diff.json": {
                "differences": [
                    item.to_dict() for item in self.response_differences
                ],
                "findings": [item.to_dict() for item in self.behavior_findings],
                "hypotheses": [
                    item.to_dict() for item in self.hypothesis_proposals
                ],
                "profiles": [item.to_dict() for item in self.response_profiles],
                "state_differences": [
                    item.to_dict() for item in self.state_differences
                ],
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebIntelligenceState":
        surface = data.get("attack_surface", {})
        return cls(
            html_analyses=[
                HTMLAnalysis.from_dict(item)
                for item in _mapping_list(data.get("html_analyses"))
            ],
            attack_surface=WebAttackSurface.from_dict(
                surface if isinstance(surface, Mapping) else {}
            ),
            technology_evidence=[
                TechnologyEvidence.from_dict(item)
                for item in _mapping_list(data.get("technology_evidence"))
            ],
            response_differences=[
                ResponseDifference.from_dict(item)
                for item in _mapping_list(data.get("response_differences"))
            ],
            behavior_findings=[
                BehaviorFinding.from_dict(item)
                for item in _mapping_list(data.get("behavior_findings"))
            ],
            hypothesis_proposals=[
                HypothesisProposal.from_dict(item)
                for item in _mapping_list(data.get("hypothesis_proposals"))
            ],
            response_profiles=[
                WebResponseProfile.from_dict(item)
                for item in _mapping_list(data.get("response_profiles"))
            ],
            state_differences=[
                WebStateDifference.from_dict(item)
                for item in _mapping_list(data.get("state_differences"))
            ],
        )


def _pairs(value: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        return ()
    pairs: list[tuple[str, str]] = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            pairs.append((str(item[0]), str(item[1])))
    return tuple(pairs)
