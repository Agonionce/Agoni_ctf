"""Typed R11 Web application, session, experiment, and evidence state."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

from agent.domains.web.intelligence.models import (
    WebResponseProfile,
    WebStateDifference,
)
from agent.intelligence.models import utc_now_iso


def _identifier(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _enum(value: object, enum_type: type[Enum], default: Enum) -> Enum:
    try:
        return enum_type(str(getattr(value, "value", value)))
    except ValueError:
        return default


def _strings(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return list(dict.fromkeys(str(item) for item in value if str(item).strip()))


def redact_web_context_text(value: object, *, explicit_secret: str = "") -> str:
    """Mask candidate values and common secret assignments in public context."""

    text = str(value)
    if explicit_secret:
        text = text.replace(explicit_secret, "<redacted>")
    text = re.sub(r"(?i)\b(?:flag|ctf)\{[^}\r\n]+\}", "<redacted>", text)
    return re.sub(
        r"(?i)\b(password|passwd|token|cookie|secret|credential|api[_-]?key)"
        r"\s*[:=]\s*([^\s,;]+)",
        r"\1=<redacted>",
        text,
    )


def redact_web_context_value(value: Any) -> Any:
    """Recursively sanitize text while preserving bounded context structure."""

    if isinstance(value, Mapping):
        return {
            str(key): redact_web_context_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_web_context_value(item) for item in value]
    if isinstance(value, str):
        return redact_web_context_text(value)
    return value


class AuthenticationStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    ANONYMOUS = "ANONYMOUS"
    AUTHENTICATED = "AUTHENTICATED"
    CHALLENGED = "CHALLENGED"
    EXPIRED = "EXPIRED"


class WebSessionStatus(str, Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    AUTHENTICATED = "AUTHENTICATED"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"


class WebExperimentType(str, Enum):
    ENDPOINT_ANALYSIS = "ENDPOINT_ANALYSIS"
    PARAMETER_BEHAVIOR = "PARAMETER_BEHAVIOR"
    AUTHENTICATION_ANALYSIS = "AUTHENTICATION_ANALYSIS"
    RESPONSE_COMPARISON = "RESPONSE_COMPARISON"
    STATE_TRANSITION = "STATE_TRANSITION"
    INPUT_BEHAVIOR_ANALYSIS = "INPUT_BEHAVIOR_ANALYSIS"
    AUTHORIZATION_ANALYSIS = "AUTHORIZATION_ANALYSIS"
    FILE_PROCESSING_ANALYSIS = "FILE_PROCESSING_ANALYSIS"
    PARSER_BEHAVIOR_ANALYSIS = "PARSER_BEHAVIOR_ANALYSIS"
    BUSINESS_LOGIC_ANALYSIS = "BUSINESS_LOGIC_ANALYSIS"


class WebEvidenceType(str, Enum):
    ENDPOINT_DISCOVERED = "ENDPOINT_DISCOVERED"
    PARAMETER_IDENTIFIED = "PARAMETER_IDENTIFIED"
    AUTHENTICATION_STATE = "AUTHENTICATION_STATE"
    SESSION_STATE = "SESSION_STATE"
    RESPONSE_BEHAVIOR = "RESPONSE_BEHAVIOR"
    STATE_TRANSITION = "STATE_TRANSITION"
    FLAG_CANDIDATE = "FLAG_CANDIDATE"
    INPUT_BEHAVIOR = "INPUT_BEHAVIOR"
    AUTHORIZATION_STATE = "AUTHORIZATION_STATE"
    FILE_PROCESSING = "FILE_PROCESSING"
    PARSER_BEHAVIOR = "PARSER_BEHAVIOR"
    BUSINESS_LOGIC = "BUSINESS_LOGIC"
    STATE_DIFFERENCE = "STATE_DIFFERENCE"


class WebFlagVerificationStatus(str, Enum):
    DETECTED = "DETECTED"
    EVIDENCE_BOUND = "EVIDENCE_BOUND"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


@dataclass
class WebEndpointModel:
    path: str
    methods: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    authentication_required: bool | None = None
    status_codes: list[int] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    response_formats: list[str] = field(default_factory=list)
    content_types: list[str] = field(default_factory=list)
    access_states: list[str] = field(default_factory=list)
    behavior_tags: list[str] = field(default_factory=list)

    def merge(
        self,
        *,
        method: str = "",
        parameters: list[str] | None = None,
        status_code: int | None = None,
        artifact_refs: list[str] | None = None,
        response_format: str = "",
        content_type: str = "",
        access_states: list[str] | None = None,
        behavior_tags: list[str] | None = None,
    ) -> None:
        if method:
            self.methods = sorted(set([*self.methods, method.upper()]))
        self.parameters = sorted(set([*self.parameters, *(parameters or [])]))
        if status_code is not None:
            self.status_codes = sorted(set([*self.status_codes, int(status_code)]))
        self.artifact_refs = list(
            dict.fromkeys([*self.artifact_refs, *(artifact_refs or [])])
        )
        if response_format:
            self.response_formats = sorted(set([*self.response_formats, response_format]))
        if content_type:
            self.content_types = sorted(set([*self.content_types, content_type]))
        self.access_states = sorted(set([*self.access_states, *(access_states or [])]))
        self.behavior_tags = sorted(set([*self.behavior_tags, *(behavior_tags or [])]))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebEndpointModel":
        return cls(
            path=str(data["path"]),
            methods=_strings(data.get("methods")),
            parameters=_strings(data.get("parameters")),
            authentication_required=(
                bool(data["authentication_required"])
                if data.get("authentication_required") is not None
                else None
            ),
            status_codes=[
                int(item) for item in data.get("status_codes", [])
                if isinstance(item, int) and not isinstance(item, bool)
            ],
            artifact_refs=_strings(data.get("artifact_refs")),
            response_formats=_strings(data.get("response_formats")),
            content_types=_strings(data.get("content_types")),
            access_states=_strings(data.get("access_states")),
            behavior_tags=_strings(data.get("behavior_tags")),
        )


@dataclass
class WebParameterModel:
    name: str
    endpoints: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    semantic_roles: list[str] = field(default_factory=list)
    value_shapes: list[str] = field(default_factory=list)
    user_controlled: bool = False
    reflected: bool = False
    affects_response: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebParameterModel":
        return cls(
            name=str(data["name"]),
            endpoints=_strings(data.get("endpoints")),
            methods=_strings(data.get("methods")),
            artifact_refs=_strings(data.get("artifact_refs")),
            locations=_strings(data.get("locations")),
            semantic_roles=_strings(data.get("semantic_roles")),
            value_shapes=_strings(data.get("value_shapes")),
            user_controlled=bool(data.get("user_controlled", False)),
            reflected=bool(data.get("reflected", False)),
            affects_response=bool(data.get("affects_response", False)),
        )


@dataclass
class WebAuthenticationModel:
    status: AuthenticationStatus = AuthenticationStatus.UNKNOWN
    active_session_id: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    mechanisms: list[str] = field(default_factory=list)
    login_endpoints: list[str] = field(default_factory=list)
    logout_endpoints: list[str] = field(default_factory=list)
    protected_endpoints: list[str] = field(default_factory=list)
    role_indicators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "active_session_id": self.active_session_id,
            "evidence_refs": list(self.evidence_refs),
            "mechanisms": list(self.mechanisms),
            "login_endpoints": list(self.login_endpoints),
            "logout_endpoints": list(self.logout_endpoints),
            "protected_endpoints": list(self.protected_endpoints),
            "role_indicators": list(self.role_indicators),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebAuthenticationModel":
        return cls(
            status=_enum(
                data.get("status"), AuthenticationStatus, AuthenticationStatus.UNKNOWN
            ),
            active_session_id=str(data.get("active_session_id", "")),
            evidence_refs=_strings(data.get("evidence_refs")),
            mechanisms=_strings(data.get("mechanisms")),
            login_endpoints=_strings(data.get("login_endpoints")),
            logout_endpoints=_strings(data.get("logout_endpoints")),
            protected_endpoints=_strings(data.get("protected_endpoints")),
            role_indicators=_strings(data.get("role_indicators")),
        )


@dataclass
class WebTechnologyModel:
    name: str
    evidence: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebTechnologyModel":
        return cls(
            name=str(data["name"]),
            evidence=_strings(data.get("evidence")),
            sources=_strings(data.get("sources")),
        )


@dataclass
class WebResponseBehavior:
    behavior_id: str
    kind: str
    endpoint: str
    summary: str
    changed: bool
    baseline_request_id: str = ""
    current_request_id: str = ""
    artifact_refs: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, *, kind: str, endpoint: str, summary: str, changed: bool,
               baseline_request_id: str = "", current_request_id: str = "",
               artifact_refs: list[str] | None = None) -> "WebResponseBehavior":
        key = f"{kind}\0{endpoint}\0{baseline_request_id}\0{current_request_id}"
        behavior_id = "behavior-" + hashlib.sha256(key.encode()).hexdigest()[:12]
        return cls(behavior_id, kind, endpoint, summary, changed,
                   baseline_request_id, current_request_id, artifact_refs or [])

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebResponseBehavior":
        return cls(
            behavior_id=str(data["behavior_id"]),
            kind=str(data["kind"]),
            endpoint=str(data.get("endpoint", "")),
            summary=str(data.get("summary", "")),
            changed=bool(data.get("changed", False)),
            baseline_request_id=str(data.get("baseline_request_id", "")),
            current_request_id=str(data.get("current_request_id", "")),
            artifact_refs=_strings(data.get("artifact_refs")),
        )


@dataclass
class WebRelationship:
    source: str
    relation: str
    target: str
    artifact_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebRelationship":
        return cls(
            source=str(data["source"]),
            relation=str(data["relation"]),
            target=str(data["target"]),
            artifact_refs=_strings(data.get("artifact_refs")),
        )


@dataclass
class WebStateTransition:
    transition_id: str
    from_state: str
    to_state: str
    event: str
    endpoint: str = ""
    artifact_refs: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        from_state: str,
        to_state: str,
        event: str,
        endpoint: str = "",
        artifact_refs: list[str] | None = None,
    ) -> "WebStateTransition":
        key = f"{from_state}\0{to_state}\0{event}\0{endpoint}"
        return cls(
            transition_id="transition-" + hashlib.sha256(key.encode()).hexdigest()[:12],
            from_state=from_state,
            to_state=to_state,
            event=event,
            endpoint=endpoint,
            artifact_refs=artifact_refs or [],
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebStateTransition":
        return cls(
            transition_id=str(data["transition_id"]),
            from_state=str(data.get("from_state", "unknown")),
            to_state=str(data.get("to_state", "unknown")),
            event=str(data.get("event", "observed response change")),
            endpoint=str(data.get("endpoint", "")),
            artifact_refs=_strings(data.get("artifact_refs")),
        )


@dataclass
class WebUserControlledInput:
    name: str
    endpoint: str
    location: str
    semantic_role: str
    value_shape: str
    reflected: bool = False
    affects_response: bool = False
    artifact_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebUserControlledInput":
        return cls(
            name=str(data["name"]),
            endpoint=str(data.get("endpoint", "")),
            location=str(data.get("location", "request")),
            semantic_role=str(data.get("semantic_role", "generic")),
            value_shape=str(data.get("value_shape", "unknown")),
            reflected=bool(data.get("reflected", False)),
            affects_response=bool(data.get("affects_response", False)),
            artifact_refs=_strings(data.get("artifact_refs")),
        )


@dataclass
class WebApplicationBehavior:
    behavior_id: str
    category: str
    endpoint: str
    observation: str
    evidence_type: str
    artifact_refs: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        category: str,
        endpoint: str,
        observation: str,
        evidence_type: str,
        artifact_refs: list[str] | None = None,
    ) -> "WebApplicationBehavior":
        key = f"{category}\0{endpoint}\0{observation}\0{evidence_type}"
        return cls(
            behavior_id="app-behavior-" + hashlib.sha256(key.encode()).hexdigest()[:12],
            category=category,
            endpoint=endpoint,
            observation=observation,
            evidence_type=evidence_type,
            artifact_refs=artifact_refs or [],
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebApplicationBehavior":
        return cls(
            behavior_id=str(data["behavior_id"]),
            category=str(data.get("category", "response")),
            endpoint=str(data.get("endpoint", "")),
            observation=str(data.get("observation", "")),
            evidence_type=str(data.get("evidence_type", "RESPONSE_BEHAVIOR")),
            artifact_refs=_strings(data.get("artifact_refs")),
        )


@dataclass
class WebApplicationModel:
    endpoints: list[WebEndpointModel] = field(default_factory=list)
    parameters: list[WebParameterModel] = field(default_factory=list)
    authentication: WebAuthenticationModel = field(default_factory=WebAuthenticationModel)
    technologies: list[WebTechnologyModel] = field(default_factory=list)
    response_behaviors: list[WebResponseBehavior] = field(default_factory=list)
    relationships: list[WebRelationship] = field(default_factory=list)
    state_transitions: list[WebStateTransition] = field(default_factory=list)
    user_controlled_inputs: list[WebUserControlledInput] = field(default_factory=list)
    application_behaviors: list[WebApplicationBehavior] = field(default_factory=list)
    response_profiles: list[WebResponseProfile] = field(default_factory=list)
    state_differences: list[WebStateDifference] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now_iso)

    def record_endpoint(self, path: str, *, method: str = "GET",
                        parameters: list[str] | None = None,
                        status_code: int | None = None,
                        artifact_refs: list[str] | None = None,
                        response_format: str = "",
                        content_type: str = "",
                        access_states: list[str] | None = None,
                        behavior_tags: list[str] | None = None) -> WebEndpointModel:
        normalized = path if path.startswith("/") else f"/{path}"
        endpoint = next((item for item in self.endpoints if item.path == normalized), None)
        if endpoint is None:
            endpoint = WebEndpointModel(normalized)
            self.endpoints.append(endpoint)
        endpoint.merge(method=method, parameters=parameters, status_code=status_code,
                       artifact_refs=artifact_refs, response_format=response_format,
                       content_type=content_type, access_states=access_states,
                       behavior_tags=behavior_tags)
        for name in parameters or []:
            parameter = next((item for item in self.parameters if item.name == name), None)
            if parameter is None:
                parameter = WebParameterModel(name)
                self.parameters.append(parameter)
            parameter.endpoints = sorted(set([*parameter.endpoints, normalized]))
            parameter.methods = sorted(set([*parameter.methods, method.upper()]))
            parameter.artifact_refs = list(dict.fromkeys([
                *parameter.artifact_refs, *(artifact_refs or [])
            ]))
            self.record_relationship(normalized, "ACCEPTS_PARAMETER", name, artifact_refs or [])
        self.endpoints.sort(key=lambda item: item.path)
        self.parameters.sort(key=lambda item: item.name)
        self.updated_at = utc_now_iso()
        return endpoint

    def record_parameter_semantics(
        self,
        name: str,
        *,
        endpoint: str,
        method: str,
        location: str,
        semantic_role: str,
        value_shape: str,
        reflected: bool = False,
        affects_response: bool = False,
        artifact_refs: list[str] | None = None,
    ) -> None:
        self.record_endpoint(
            endpoint,
            method=method,
            parameters=[name],
            artifact_refs=artifact_refs,
        )
        parameter = next(item for item in self.parameters if item.name == name)
        parameter.locations = sorted(set([*parameter.locations, location]))
        parameter.semantic_roles = sorted(set([*parameter.semantic_roles, semantic_role]))
        parameter.value_shapes = sorted(set([*parameter.value_shapes, value_shape]))
        parameter.user_controlled = True
        parameter.reflected = parameter.reflected or reflected
        parameter.affects_response = parameter.affects_response or affects_response
        key = (name, endpoint, location)
        existing = next(
            (
                item for item in self.user_controlled_inputs
                if (item.name, item.endpoint, item.location) == key
            ),
            None,
        )
        if existing is None:
            self.user_controlled_inputs.append(WebUserControlledInput(
                name=name,
                endpoint=endpoint,
                location=location,
                semantic_role=semantic_role,
                value_shape=value_shape,
                reflected=reflected,
                affects_response=affects_response,
                artifact_refs=artifact_refs or [],
            ))
        else:
            existing.reflected = existing.reflected or reflected
            existing.affects_response = existing.affects_response or affects_response
            existing.artifact_refs = list(dict.fromkeys([
                *existing.artifact_refs, *(artifact_refs or [])
            ]))
        self.user_controlled_inputs.sort(
            key=lambda item: (item.endpoint, item.name, item.location)
        )
        self.updated_at = utc_now_iso()

    def record_transition(self, transition: WebStateTransition) -> None:
        existing = next(
            (item for item in self.state_transitions
             if item.transition_id == transition.transition_id),
            None,
        )
        if existing is None:
            self.state_transitions.append(transition)
        else:
            existing.artifact_refs = list(dict.fromkeys([
                *existing.artifact_refs, *transition.artifact_refs
            ]))
        self.state_transitions.sort(key=lambda item: item.transition_id)
        self.updated_at = utc_now_iso()

    def record_application_behavior(self, behavior: WebApplicationBehavior) -> None:
        existing = next(
            (item for item in self.application_behaviors
             if item.behavior_id == behavior.behavior_id),
            None,
        )
        if existing is None:
            self.application_behaviors.append(behavior)
        else:
            existing.artifact_refs = list(dict.fromkeys([
                *existing.artifact_refs, *behavior.artifact_refs
            ]))
        self.application_behaviors.sort(key=lambda item: item.behavior_id)
        self.updated_at = utc_now_iso()

    def record_technology(self, name: str, *, evidence: str = "", source: str = "") -> None:
        item = next((entry for entry in self.technologies if entry.name == name), None)
        if item is None:
            item = WebTechnologyModel(name)
            self.technologies.append(item)
        if evidence and evidence not in item.evidence:
            item.evidence.append(evidence[:500])
        if source and source not in item.sources:
            item.sources.append(source[:500])
        self.technologies.sort(key=lambda entry: entry.name.lower())
        self.updated_at = utc_now_iso()

    def record_relationship(self, source: str, relation: str, target: str,
                            artifact_refs: list[str] | None = None) -> None:
        item = next((entry for entry in self.relationships
                     if (entry.source, entry.relation, entry.target) ==
                     (source, relation, target)), None)
        if item is None:
            item = WebRelationship(source, relation, target)
            self.relationships.append(item)
        item.artifact_refs = list(dict.fromkeys([
            *item.artifact_refs, *(artifact_refs or [])
        ]))
        self.relationships.sort(key=lambda entry: (entry.source, entry.relation, entry.target))
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoints": [asdict(item) for item in self.endpoints],
            "parameters": [asdict(item) for item in self.parameters],
            "authentication": self.authentication.to_dict(),
            "technologies": [asdict(item) for item in self.technologies],
            "response_behaviors": [asdict(item) for item in self.response_behaviors],
            "relationships": [asdict(item) for item in self.relationships],
            "state_transitions": [asdict(item) for item in self.state_transitions],
            "user_controlled_inputs": [asdict(item) for item in self.user_controlled_inputs],
            "application_behaviors": [asdict(item) for item in self.application_behaviors],
            "response_profiles": [item.to_dict() for item in self.response_profiles],
            "state_differences": [item.to_dict() for item in self.state_differences],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebApplicationModel":
        def items(name: str) -> list[Mapping[str, Any]]:
            raw = data.get(name, [])
            return [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []
        authentication = data.get("authentication", {})
        return cls(
            endpoints=[WebEndpointModel.from_dict(item) for item in items("endpoints")],
            parameters=[WebParameterModel.from_dict(item) for item in items("parameters")],
            authentication=WebAuthenticationModel.from_dict(
                authentication if isinstance(authentication, Mapping) else {}
            ),
            technologies=[WebTechnologyModel.from_dict(item) for item in items("technologies")],
            response_behaviors=[WebResponseBehavior.from_dict(item) for item in items("response_behaviors")],
            relationships=[WebRelationship.from_dict(item) for item in items("relationships")],
            state_transitions=[WebStateTransition.from_dict(item) for item in items("state_transitions")],
            user_controlled_inputs=[WebUserControlledInput.from_dict(item) for item in items("user_controlled_inputs")],
            application_behaviors=[WebApplicationBehavior.from_dict(item) for item in items("application_behaviors")],
            response_profiles=[WebResponseProfile.from_dict(item) for item in items("response_profiles")],
            state_differences=[WebStateDifference.from_dict(item) for item in items("state_differences")],
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )


@dataclass
class WebSessionState:
    session_id: str
    origin: str
    status: WebSessionStatus = WebSessionStatus.CREATED
    authentication_status: AuthenticationStatus = AuthenticationStatus.UNKNOWN
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    csrf_tokens: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", self.session_id) is None:
            raise ValueError("Web session_id must be a normalized opaque identifier")
        if not self.origin.strip():
            raise ValueError("Web session origin must be non-empty")
        if not isinstance(self.status, WebSessionStatus):
            raise ValueError("Web session status is invalid")
        if not isinstance(self.authentication_status, AuthenticationStatus):
            raise ValueError("Web authentication status is invalid")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["authentication_status"] = self.authentication_status.value
        return payload

    def safe_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "origin": self.origin,
            "status": self.status.value,
            "authentication_status": self.authentication_status.value,
            "cookie_names": sorted(self.cookies),
            "header_names": sorted(self.headers),
            "csrf_token_names": sorted(self.csrf_tokens),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebSessionState":
        def mapping(name: str) -> dict[str, str]:
            raw = data.get(name, {})
            return {str(key): str(value) for key, value in raw.items()} if isinstance(raw, Mapping) else {}
        return cls(
            session_id=str(data["session_id"]),
            origin=str(data["origin"]),
            status=_enum(data.get("status"), WebSessionStatus, WebSessionStatus.CREATED),
            authentication_status=_enum(
                data.get("authentication_status"), AuthenticationStatus,
                AuthenticationStatus.UNKNOWN,
            ),
            cookies=mapping("cookies"), headers=mapping("headers"),
            csrf_tokens=mapping("csrf_tokens"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )


@dataclass
class WebExperimentRecord:
    experiment_id: str
    hypothesis_id: str
    experiment_type: WebExperimentType
    goal: str
    expected_observation: str
    evidence_type: WebEvidenceType
    status: str
    context: dict[str, Any] = field(default_factory=dict)
    evaluation: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    experience_influence: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        for name in ("experiment_id", "hypothesis_id", "goal", "expected_observation", "status"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"Web experiment {name} must be non-empty")
        if not isinstance(self.experiment_type, WebExperimentType):
            raise ValueError("Web experiment type is invalid")
        if not isinstance(self.evidence_type, WebEvidenceType):
            raise ValueError("Web experiment evidence type is invalid")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["experiment_type"] = self.experiment_type.value
        payload["evidence_type"] = self.evidence_type.value
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebExperimentRecord":
        return cls(
            experiment_id=str(data["experiment_id"]),
            hypothesis_id=str(data["hypothesis_id"]),
            experiment_type=_enum(data.get("experiment_type"), WebExperimentType,
                                  WebExperimentType.ENDPOINT_ANALYSIS),
            goal=str(data.get("goal", "")),
            expected_observation=str(data.get("expected_observation", "")),
            evidence_type=_enum(data.get("evidence_type"), WebEvidenceType,
                                WebEvidenceType.RESPONSE_BEHAVIOR),
            status=str(data.get("status", "UNKNOWN")),
            context=(
                {str(key): value for key, value in data.get("context", {}).items()}
                if isinstance(data.get("context"), Mapping)
                else {}
            ),
            evaluation=str(data.get("evaluation", "")),
            evidence_ids=_strings(data.get("evidence_ids")),
            experience_influence=_strings(data.get("experience_influence")),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )


@dataclass
class WebEvidenceRecord:
    evidence_type: WebEvidenceType
    observation: str
    artifact_refs: list[str]
    evidence_id: str = field(default_factory=lambda: _identifier("web-evidence"))
    request_id: str = ""
    experiment_id: str = ""
    observation_id: str = ""
    endpoint: str = ""
    parameter: str = ""
    timestamp: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.observation.strip() or not self.artifact_refs:
            raise ValueError("Web evidence requires an observation and artifact provenance")
        if not isinstance(self.evidence_type, WebEvidenceType):
            raise ValueError("Web evidence type is invalid")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_type"] = self.evidence_type.value
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebEvidenceRecord":
        return cls(
            evidence_id=str(data.get("evidence_id") or _identifier("web-evidence")),
            evidence_type=_enum(data.get("evidence_type"), WebEvidenceType,
                                WebEvidenceType.RESPONSE_BEHAVIOR),
            observation=str(data["observation"]),
            artifact_refs=_strings(data.get("artifact_refs")),
            request_id=str(data.get("request_id", "")),
            experiment_id=str(data.get("experiment_id", "")),
            observation_id=str(data.get("observation_id", "")),
            endpoint=str(data.get("endpoint", "")),
            parameter=str(data.get("parameter", "")),
            timestamp=str(data.get("timestamp") or utc_now_iso()),
        )


@dataclass
class WebFlagCandidate:
    value: str
    source: str
    confidence: float
    evidence_summary: str
    artifact_refs: list[str]
    candidate_id: str = field(default_factory=lambda: _identifier("web-flag"))
    verification_status: WebFlagVerificationStatus = WebFlagVerificationStatus.DETECTED
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.value.strip() or not self.source.strip():
            raise ValueError("Web flag candidate requires a value and source")
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ) or not 0 <= float(self.confidence) <= 1:
            raise ValueError("Web flag candidate confidence must be in [0, 1]")
        if not isinstance(self.verification_status, WebFlagVerificationStatus):
            raise ValueError("Web flag candidate verification status is invalid")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verification_status"] = self.verification_status.value
        return payload

    def safe_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "value_digest": hashlib.sha256(self.value.encode()).hexdigest()[:12],
            "source": redact_web_context_text(
                self.source[:500], explicit_secret=self.value
            ),
            "confidence": self.confidence,
            "evidence_summary": redact_web_context_text(
                self.evidence_summary[:500], explicit_secret=self.value
            ),
            "artifact_refs": list(self.artifact_refs),
            "verification_status": self.verification_status.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebFlagCandidate":
        return cls(
            candidate_id=str(data.get("candidate_id") or _identifier("web-flag")),
            value=str(data["value"]), source=str(data["source"]),
            confidence=float(data.get("confidence", 0.0)),
            evidence_summary=str(data.get("evidence_summary", "")),
            artifact_refs=_strings(data.get("artifact_refs")),
            verification_status=_enum(
                data.get("verification_status"), WebFlagVerificationStatus,
                WebFlagVerificationStatus.DETECTED,
            ),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )
