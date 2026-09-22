"""Pure R11 Web experiment definitions and phase-driven proposals."""

from __future__ import annotations

from dataclasses import dataclass

from agent.domains.web.research.models import (
    AuthenticationStatus,
    WebApplicationModel,
    WebEvidenceType,
    WebExperimentType,
    WebSessionState,
)


@dataclass(frozen=True)
class WebExperimentDefinition:
    experiment_type: WebExperimentType
    goal_template: str
    context_template: str
    expected_observation: str
    evidence_type: WebEvidenceType

    def proposal(self, *, subject: str, statement: str, confidence: float,
                 priority: str, evidence_value: float) -> dict[str, object]:
        return {
            "statement": statement,
            "confidence": confidence,
            "priority": priority,
            "goal": self.goal_template.format(subject=subject),
            "context": {
                "subject": subject,
                "research_question": self.context_template.format(subject=subject),
                "boundary": "captured evidence or explicitly authorized local behavior only",
            },
            "expected_result": self.expected_observation,
            "evidence_value": evidence_value,
            "experiment_type": self.experiment_type.value,
            "evidence_type": self.evidence_type.value,
        }


class WebExperimentCatalog:
    """Describe what to observe; it deliberately contains no payload or Tool call."""

    DEFINITIONS = {
        WebExperimentType.ENDPOINT_ANALYSIS: WebExperimentDefinition(
            WebExperimentType.ENDPOINT_ANALYSIS,
            "establish a bounded baseline response profile for {subject}",
            "What structural behavior does {subject} expose?",
            "baseline response characteristics recorded",
            WebEvidenceType.ENDPOINT_DISCOVERED,
        ),
        WebExperimentType.PARAMETER_BEHAVIOR: WebExperimentDefinition(
            WebExperimentType.PARAMETER_BEHAVIOR,
            "compare authorized local response behavior for {subject}",
            "Does controlled input at {subject} change the observed response?",
            "response behavior changed",
            WebEvidenceType.RESPONSE_BEHAVIOR,
        ),
        WebExperimentType.AUTHENTICATION_ANALYSIS: WebExperimentDefinition(
            WebExperimentType.AUTHENTICATION_ANALYSIS,
            "observe authentication requirements for {subject}",
            "Which authentication state is required by {subject}?",
            "authentication state recorded",
            WebEvidenceType.AUTHENTICATION_STATE,
        ),
        WebExperimentType.RESPONSE_COMPARISON: WebExperimentDefinition(
            WebExperimentType.RESPONSE_COMPARISON,
            "compare two captured responses for {subject}",
            "Which structural fields differ between captured responses for {subject}?",
            "response behavior changed",
            WebEvidenceType.RESPONSE_BEHAVIOR,
        ),
        WebExperimentType.STATE_TRANSITION: WebExperimentDefinition(
            WebExperimentType.STATE_TRANSITION,
            "observe the authorized state transition for {subject}",
            "Which state transition is evidenced for {subject}?",
            "state transition recorded",
            WebEvidenceType.STATE_TRANSITION,
        ),
        WebExperimentType.INPUT_BEHAVIOR_ANALYSIS: WebExperimentDefinition(
            WebExperimentType.INPUT_BEHAVIOR_ANALYSIS,
            "characterize bounded input behavior for {subject}",
            "How is {subject} interpreted and which response structure changes?",
            "input behavior recorded",
            WebEvidenceType.INPUT_BEHAVIOR,
        ),
        WebExperimentType.AUTHORIZATION_ANALYSIS: WebExperimentDefinition(
            WebExperimentType.AUTHORIZATION_ANALYSIS,
            "compare authorized access states for {subject}",
            "Which access state governs {subject}?",
            "authorization state difference recorded",
            WebEvidenceType.AUTHORIZATION_STATE,
        ),
        WebExperimentType.FILE_PROCESSING_ANALYSIS: WebExperimentDefinition(
            WebExperimentType.FILE_PROCESSING_ANALYSIS,
            "characterize local file-processing behavior for {subject}",
            "Which accepted shape and processing outcome are evidenced for {subject}?",
            "file-processing behavior recorded",
            WebEvidenceType.FILE_PROCESSING,
        ),
        WebExperimentType.PARSER_BEHAVIOR_ANALYSIS: WebExperimentDefinition(
            WebExperimentType.PARSER_BEHAVIOR_ANALYSIS,
            "characterize parser response behavior for {subject}",
            "Which response format or parser error pattern is evidenced for {subject}?",
            "parser behavior recorded",
            WebEvidenceType.PARSER_BEHAVIOR,
        ),
        WebExperimentType.BUSINESS_LOGIC_ANALYSIS: WebExperimentDefinition(
            WebExperimentType.BUSINESS_LOGIC_ANALYSIS,
            "observe bounded business-state behavior for {subject}",
            "Which application state difference is evidenced for {subject}?",
            "business-state behavior recorded",
            WebEvidenceType.BUSINESS_LOGIC,
        ),
    }

    def proposals(
        self,
        model: WebApplicationModel,
        sessions: list[WebSessionState],
        phase: str,
    ) -> list[dict[str, object]]:
        proposals: list[dict[str, object]] = []
        if phase == "RECON":
            for endpoint in model.endpoints[:3]:
                proposals.append(self.DEFINITIONS[WebExperimentType.ENDPOINT_ANALYSIS].proposal(
                    subject=endpoint.path,
                    statement=f"Endpoint {endpoint.path} has behavior that should be characterized.",
                    confidence=0.45, priority="HIGH", evidence_value=0.7,
                ))
        if phase in {"ANALYSIS", "EXPLOITATION", "VERIFY"}:
            for parameter in model.parameters[:3]:
                location = parameter.endpoints[0] if parameter.endpoints else "an observed endpoint"
                proposals.append(self.DEFINITIONS[WebExperimentType.PARAMETER_BEHAVIOR].proposal(
                    subject=f"parameter {parameter.name} at {location}",
                    statement=f"Parameter {parameter.name} at {location} affects response behavior.",
                    confidence=0.5, priority="MEDIUM", evidence_value=0.7,
                ))
                experiment_type = (
                    WebExperimentType.FILE_PROCESSING_ANALYSIS
                    if "file" in parameter.semantic_roles
                    else WebExperimentType.BUSINESS_LOGIC_ANALYSIS
                    if "business" in parameter.semantic_roles
                    else WebExperimentType.INPUT_BEHAVIOR_ANALYSIS
                )
                proposals.append(self.DEFINITIONS[experiment_type].proposal(
                    subject=f"parameter {parameter.name} at {location}",
                    statement=(
                        f"Parameter {parameter.name} at {location} has "
                        f"{parameter.semantic_roles[0] if parameter.semantic_roles else 'input'} behavior "
                        "that should be characterized."
                    ),
                    confidence=0.55, priority="HIGH", evidence_value=0.8,
                ))
        if model.authentication.status in {
            AuthenticationStatus.UNKNOWN,
            AuthenticationStatus.CHALLENGED,
        } and model.endpoints:
            proposals.append(self.DEFINITIONS[WebExperimentType.AUTHENTICATION_ANALYSIS].proposal(
                subject=model.endpoints[0].path,
                statement="The observed Web flow has an authentication state that affects access.",
                confidence=0.4, priority="MEDIUM", evidence_value=0.65,
            ))
        for endpoint in model.authentication.protected_endpoints[:2]:
            proposals.append(self.DEFINITIONS[WebExperimentType.AUTHORIZATION_ANALYSIS].proposal(
                subject=endpoint,
                statement=f"Endpoint {endpoint} has access-state behavior that should be compared.",
                confidence=0.6, priority="HIGH", evidence_value=0.85,
            ))
        for profile in model.response_profiles[-2:]:
            if profile.response_format == "JSON" or any(
                item in {"parser_error", "template_error", "database_error"}
                for item in profile.error_patterns
            ):
                proposals.append(self.DEFINITIONS[WebExperimentType.PARSER_BEHAVIOR_ANALYSIS].proposal(
                    subject=profile.url,
                    statement="The captured response exposes parser behavior that should be characterized.",
                    confidence=0.5, priority="MEDIUM", evidence_value=0.7,
                ))
        for behavior in model.application_behaviors[-3:]:
            if behavior.category == "business_logic":
                proposals.append(self.DEFINITIONS[WebExperimentType.BUSINESS_LOGIC_ANALYSIS].proposal(
                    subject=behavior.endpoint or "the observed application flow",
                    statement="The application exposes a business-state transition that should be characterized.",
                    confidence=0.55, priority="HIGH", evidence_value=0.8,
                ))
        if sessions and any(item.authentication_status is AuthenticationStatus.AUTHENTICATED
                            for item in sessions):
            proposals.append(self.DEFINITIONS[WebExperimentType.STATE_TRANSITION].proposal(
                subject="the authenticated session",
                statement="The authenticated session enables an observable state transition.",
                confidence=0.5, priority="MEDIUM", evidence_value=0.7,
            ))
        return proposals[:8]
