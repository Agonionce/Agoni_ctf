"""R12 projection from passive response intelligence to Web knowledge."""

from __future__ import annotations

from urllib.parse import urlsplit

from agent.domains.web.intelligence.models import (
    WebIntelligenceState,
    WebResponseProfile,
    WebStateDifference,
)
from agent.domains.web.research.models import (
    AuthenticationStatus,
    WebApplicationBehavior,
    WebApplicationModel,
    WebStateTransition,
)


class WebKnowledgeModelEnhancer:
    """Build bounded semantics from captured structure, never from secret values."""

    ROLE_NAMES = {
        "identifier": {"id", "item_id", "user_id", "order_id", "post_id"},
        "identity": {"username", "user", "email", "account"},
        "credential": {"password", "passwd", "passcode"},
        "file": {"file", "upload", "path", "filename", "image", "archive"},
        "navigation": {"url", "redirect", "next", "return", "continue"},
        "business": {"action", "mode", "quantity", "amount", "price", "coupon", "role"},
        "pagination": {"page", "limit", "offset"},
        "state_token": {"csrf", "csrf_token", "xsrf", "nonce"},
    }

    def synchronize(
        self,
        model: WebApplicationModel,
        intelligence: WebIntelligenceState,
        *,
        artifact_refs: list[str] | None = None,
    ) -> None:
        references = artifact_refs or []
        for profile in intelligence.response_profiles:
            self.ingest_profile(model, profile, artifact_refs=references)
        for difference in intelligence.state_differences:
            self.ingest_difference(
                model,
                difference,
                artifact_refs=references,
            )
        for difference in intelligence.response_differences:
            if not (
                difference.status_changed
                or difference.content_changed
                or difference.title_changed
                or difference.length_difference != 0
            ):
                continue
            self._behavior(
                model,
                category="response_difference",
                endpoint="",
                observation=(
                    f"Captured responses {difference.baseline_request_id} and "
                    f"{difference.current_request_id} differ in bounded response characteristics."
                ),
                evidence_type="RESPONSE_BEHAVIOR",
                artifact_refs=references,
            )

    def ingest_profile(
        self,
        model: WebApplicationModel,
        profile: WebResponseProfile,
        *,
        artifact_refs: list[str] | None = None,
        method: str = "GET",
    ) -> None:
        references = artifact_refs or []
        path = urlsplit(profile.url).path or "/"
        locations = dict(profile.parameter_locations)
        shapes = dict(profile.parameter_shapes)
        access_states = list(profile.state_markers)
        behavior_tags = [
            *profile.error_patterns,
            f"format:{profile.response_format.lower()}",
        ]
        endpoint = model.record_endpoint(
            path,
            method=method,
            parameters=list(profile.parameter_names),
            status_code=profile.status_code,
            artifact_refs=references,
            response_format=profile.response_format,
            content_type=profile.content_type,
            access_states=access_states,
            behavior_tags=behavior_tags,
        )
        for name in profile.parameter_names:
            role = self.semantic_role(name)
            model.record_parameter_semantics(
                name,
                endpoint=path,
                method=method,
                location=locations.get(name, "request"),
                semantic_role=role,
                value_shape=shapes.get(name, "unknown"),
                artifact_refs=references,
            )
            self._behavior(
                model,
                category="input_behavior",
                endpoint=path,
                observation=f"User-controlled input {name} was observed at {path}.",
                evidence_type="INPUT_BEHAVIOR",
                artifact_refs=references,
            )
            if role == "file":
                self._behavior(
                    model,
                    category="file_processing",
                    endpoint=path,
                    observation=f"Input {name} has file-processing semantics.",
                    evidence_type="FILE_PROCESSING",
                    artifact_refs=references,
                )
            if role == "business":
                self._behavior(
                    model,
                    category="business_logic",
                    endpoint=path,
                    observation=f"Input {name} has business-state semantics.",
                    evidence_type="BUSINESS_LOGIC",
                    artifact_refs=references,
                )
        for contract in profile.client_requests:
            contract_parameters = [
                *(name for name, _value in contract.query),
                *(name for name, _value in contract.json_body),
            ]
            model.record_endpoint(
                contract.path,
                method=contract.method,
                parameters=contract_parameters,
                artifact_refs=references,
                response_format="CLIENT_REQUEST_CONTRACT",
            )
            for name, value in [*contract.query, *contract.json_body]:
                model.record_parameter_semantics(
                    name,
                    endpoint=contract.path,
                    method=contract.method,
                    location="query" if (name, value) in contract.query else "json",
                    semantic_role=self.semantic_role(name),
                    value_shape=self._shape(value),
                    artifact_refs=references,
                )
            self._behavior(
                model,
                category="client_request_contract",
                endpoint=contract.path,
                observation=(
                    f"Static client code declares {contract.method} {contract.path} "
                    f"with {len(contract.query)} query and {len(contract.json_body)} JSON fields."
                ),
                evidence_type="RESPONSE_BEHAVIOR",
                artifact_refs=references,
            )
        if profile.response_format in {"JSON", "HTML"}:
            self._behavior(
                model,
                category="structured_response",
                endpoint=path,
                observation=(
                    f"{profile.response_format} response structure observed; "
                    f"json_keys={len(profile.json_keys)}; forms={profile.html_form_count}."
                ),
                evidence_type="RESPONSE_BEHAVIOR",
                artifact_refs=references,
            )
        for pattern in profile.error_patterns:
            category = (
                "file_processing" if pattern == "file_processing_error"
                else "parser_behavior" if pattern in {
                    "parser_error", "template_error", "database_error", "stack_trace"
                }
                else "access_control" if pattern in {
                    "authentication_error", "authorization_error"
                }
                else "input_validation"
            )
            self._behavior(
                model,
                category=category,
                endpoint=path,
                observation=f"Response matched structural error pattern: {pattern}.",
                evidence_type=(
                    "PARSER_BEHAVIOR" if category == "parser_behavior"
                    else "FILE_PROCESSING" if category == "file_processing"
                    else "AUTHORIZATION_STATE" if category == "access_control"
                    else "INPUT_BEHAVIOR"
                ),
                artifact_refs=references,
            )
        self._authentication(model, profile, path, references)
        profiles = {item.request_id: item for item in model.response_profiles}
        profiles[profile.request_id] = profile
        model.response_profiles = list(profiles.values())[-50:]

    def ingest_difference(
        self,
        model: WebApplicationModel,
        difference: WebStateDifference,
        *,
        artifact_refs: list[str] | None = None,
    ) -> None:
        references = artifact_refs or []
        differences = {
            (item.baseline_request_id, item.current_request_id): item
            for item in model.state_differences
        }
        differences[(difference.baseline_request_id, difference.current_request_id)] = difference
        model.state_differences = list(differences.values())[-50:]
        if not difference.changed:
            return
        profiles = {item.request_id: item for item in model.response_profiles}
        before = profiles.get(difference.baseline_request_id)
        after = profiles.get(difference.current_request_id)
        from_state = self._state(before)
        to_state = self._state(after)
        endpoint = urlsplit(after.url).path if after is not None else ""
        transition = WebStateTransition.create(
            from_state=from_state,
            to_state=to_state,
            event=f"response {difference.current_request_id}",
            endpoint=endpoint,
            artifact_refs=references,
        )
        model.record_transition(transition)
        self._behavior(
            model,
            category="state_difference",
            endpoint=endpoint,
            observation=(
                f"Structural state difference observed from {difference.baseline_request_id} "
                f"to {difference.current_request_id}."
            ),
            evidence_type="STATE_DIFFERENCE",
            artifact_refs=references,
        )
        changed_parameters: set[str] = set()
        if before is not None:
            changed_parameters.update(before.parameter_names)
        if after is not None:
            changed_parameters.update(after.parameter_names)
        for parameter in model.parameters:
            if parameter.name in changed_parameters:
                parameter.affects_response = True
        for item in model.user_controlled_inputs:
            if item.name in changed_parameters:
                item.affects_response = True

    @classmethod
    def semantic_role(cls, name: str) -> str:
        normalized = name.lower().strip()
        for role, names in cls.ROLE_NAMES.items():
            if normalized in names or any(normalized.endswith(f"_{item}") for item in names):
                return role
        return "generic"

    @staticmethod
    def _shape(value: str) -> str:
        text = str(value).strip()
        if not text:
            return "empty"
        if text.lower() in {"true", "false"}:
            return "boolean"
        if text.lstrip("-").isdigit():
            return "integer"
        if "/" in text or "\\" in text:
            return "path-like"
        return "text"

    @staticmethod
    def _state(profile: WebResponseProfile | None) -> str:
        if profile is None:
            return "unknown"
        for preferred in (
            "authenticated", "anonymous", "authorization_challenged",
            "state_changed", "success", "failure",
        ):
            if preferred in profile.state_markers:
                return preferred
        return f"http_{profile.status_code}" if profile.status_code is not None else "unknown"

    @staticmethod
    def _behavior(
        model: WebApplicationModel,
        *,
        category: str,
        endpoint: str,
        observation: str,
        evidence_type: str,
        artifact_refs: list[str],
    ) -> None:
        model.record_application_behavior(WebApplicationBehavior.create(
            category=category,
            endpoint=endpoint,
            observation=observation,
            evidence_type=evidence_type,
            artifact_refs=artifact_refs,
        ))

    @staticmethod
    def _authentication(
        model: WebApplicationModel,
        profile: WebResponseProfile,
        path: str,
        references: list[str],
    ) -> None:
        auth = model.authentication
        lowered = path.lower()
        if "login" in lowered or "signin" in lowered:
            auth.login_endpoints = sorted(set([*auth.login_endpoints, path]))
        if "logout" in lowered or "signout" in lowered:
            auth.logout_endpoints = sorted(set([*auth.logout_endpoints, path]))
        if profile.html_form_count and ("login" in lowered or "signin" in lowered):
            auth.mechanisms = sorted(set([*auth.mechanisms, "form"] ))
        if any(name in {"csrf", "csrf_token", "xsrf", "nonce"}
               for name in profile.parameter_names):
            auth.mechanisms = sorted(set([*auth.mechanisms, "state_token"] ))
        if profile.status_code in {401, 403} or any(
            item in profile.error_patterns
            for item in ("authentication_error", "authorization_error")
        ):
            auth.status = AuthenticationStatus.CHALLENGED
            auth.protected_endpoints = sorted(set([*auth.protected_endpoints, path]))
            endpoint = next((item for item in model.endpoints if item.path == path), None)
            if endpoint is not None:
                endpoint.authentication_required = True
        elif "authenticated" in profile.state_markers:
            auth.status = AuthenticationStatus.AUTHENTICATED
        elif "anonymous" in profile.state_markers and auth.status is AuthenticationStatus.UNKNOWN:
            auth.status = AuthenticationStatus.ANONYMOUS
        role_names = {
            key.split(".")[-1].replace("[]", "")
            for key in profile.json_keys
        } & {"role", "roles", "admin", "permission", "permissions"}
        auth.role_indicators = sorted(set([*auth.role_indicators, *role_names]))
        auth.evidence_refs = list(dict.fromkeys([*auth.evidence_refs, *references]))
