"""R5 typed Web lifecycle state, separate from RunState and IntelligenceState."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from agent.domains.base.runtime import DomainRuntimeState
from agent.domains.web.intelligence.models import WebIntelligenceState
from agent.domains.web.research.models import (
    WebApplicationModel,
    WebEvidenceRecord,
    WebExperimentRecord,
    WebFlagCandidate,
    WebSessionState,
    redact_web_context_value,
)


@dataclass(frozen=True)
class WebRuntimeMetadata:
    declared_entry_points: tuple[str, ...] = ()
    declared_session_model: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class WebRuntimeState(DomainRuntimeState):
    """Web-specific observations; it contains no step or reasoning history."""

    base_url: str | None = None
    endpoints: list[str] = field(default_factory=list)
    parameters: dict[str, list[str]] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    technologies: list[str] = field(default_factory=list)
    web_intelligence: WebIntelligenceState = field(
        default_factory=WebIntelligenceState
    )
    application_model: WebApplicationModel = field(
        default_factory=WebApplicationModel
    )
    sessions: list[WebSessionState] = field(default_factory=list)
    web_experiments: list[WebExperimentRecord] = field(default_factory=list)
    web_evidence: list[WebEvidenceRecord] = field(default_factory=list)
    flag_candidates: list[WebFlagCandidate] = field(default_factory=list)

    @property
    def current_phase(self) -> str:
        return self.phase

    def record_endpoint(self, endpoint: str) -> None:
        if endpoint and endpoint not in self.endpoints:
            self.endpoints.append(endpoint)
            self.endpoints.sort()

    def record_parameter(self, name: str, endpoint: str) -> None:
        if not name:
            return
        locations = self.parameters.setdefault(name, [])
        if endpoint and endpoint not in locations:
            locations.append(endpoint)
            locations.sort()

    def record_technology(self, technology: str) -> None:
        if technology and technology not in self.technologies:
            self.technologies.append(technology)
            self.technologies.sort()

    def safe_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload["cookies"] = sorted(self.cookies)
        payload["sessions"] = [item.safe_dict() for item in self.sessions]
        payload["flag_candidates"] = [
            item.safe_dict() for item in self.flag_candidates
        ]
        safe = redact_web_context_value(payload)
        return safe if isinstance(safe, dict) else {}

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["web_intelligence"] = self.web_intelligence.to_dict()
        payload["application_model"] = self.application_model.to_dict()
        payload["sessions"] = [item.to_dict() for item in self.sessions]
        payload["web_experiments"] = [
            item.to_dict() for item in self.web_experiments
        ]
        payload["web_evidence"] = [item.to_dict() for item in self.web_evidence]
        payload["flag_candidates"] = [
            item.to_dict() for item in self.flag_candidates
        ]
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebRuntimeState":
        base = DomainRuntimeState.from_dict(data)
        raw_endpoints = data.get("endpoints", [])
        raw_parameters = data.get("parameters", {})
        raw_cookies = data.get("cookies", {})
        raw_technologies = data.get("technologies", [])
        raw_web_intelligence = data.get("web_intelligence", {})
        raw_application_model = data.get("application_model", {})

        def mappings(name: str) -> list[Mapping[str, Any]]:
            raw = data.get(name, [])
            if not isinstance(raw, list):
                return []
            return [item for item in raw if isinstance(item, Mapping)]

        state = cls(
            domain=base.domain,
            phase=base.phase,
            challenge_id=base.challenge_id,
            phase_history=base.phase_history,
            details=base.details,
            observation_count=base.observation_count,
            last_observation=base.last_observation,
            initialized_at=base.initialized_at,
            updated_at=base.updated_at,
            base_url=(str(data["base_url"]) if data.get("base_url") else None),
            endpoints=(
                [str(item) for item in raw_endpoints]
                if isinstance(raw_endpoints, list)
                else []
            ),
            parameters=(
                {
                    str(name): [str(location) for location in locations]
                    for name, locations in raw_parameters.items()
                    if isinstance(locations, list)
                }
                if isinstance(raw_parameters, Mapping)
                else {}
            ),
            cookies=(
                {str(name): str(value) for name, value in raw_cookies.items()}
                if isinstance(raw_cookies, Mapping)
                else {}
            ),
            technologies=(
                [str(item) for item in raw_technologies]
                if isinstance(raw_technologies, list)
                else []
            ),
            web_intelligence=WebIntelligenceState.from_dict(
                raw_web_intelligence
                if isinstance(raw_web_intelligence, Mapping)
                else {}
            ),
            application_model=WebApplicationModel.from_dict(
                raw_application_model
                if isinstance(raw_application_model, Mapping)
                else {}
            ),
            sessions=[
                WebSessionState.from_dict(item) for item in mappings("sessions")
            ],
            web_experiments=[
                WebExperimentRecord.from_dict(item)
                for item in mappings("web_experiments")
            ],
            web_evidence=[
                WebEvidenceRecord.from_dict(item)
                for item in mappings("web_evidence")
            ],
            flag_candidates=[
                WebFlagCandidate.from_dict(item)
                for item in mappings("flag_candidates")
            ],
        )
        if not state.application_model.endpoints:
            for endpoint in state.endpoints:
                endpoint_parameters = [
                    name for name, locations in state.parameters.items()
                    if endpoint in locations
                ]
                state.application_model.record_endpoint(
                    endpoint,
                    parameters=endpoint_parameters,
                )
            for technology in state.technologies:
                state.application_model.record_technology(
                    technology,
                    evidence="restored legacy WebRuntimeState",
                    source="domain_runtime.json",
                )
        return state
