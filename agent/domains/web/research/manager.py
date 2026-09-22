"""Pure R11 coordinator that projects observations into Web research state."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domains.web.intelligence.models import WebResponseProfile
from agent.domains.web.research.evidence import WebEvidenceFactory
from agent.domains.web.research.knowledge import WebKnowledgeModelEnhancer
from agent.domains.web.research.models import (
    AuthenticationStatus,
    WebExperimentRecord,
    WebExperimentType,
    WebEvidenceType,
    WebFlagCandidate,
    WebFlagVerificationStatus,
    WebResponseBehavior,
)
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.models import utc_now_iso
from agent.runtime.contracts import AnalysisResult, DecisionType, Observation


class WebResearchManager:
    """Update only WebRuntimeState; no Tool, socket, or approval capability exists here."""

    def __init__(self, state: WebRuntimeState) -> None:
        self.state = state
        self.evidence_factory = WebEvidenceFactory()
        self.knowledge_enhancer = WebKnowledgeModelEnhancer()

    def observe(self, observation: Observation, analysis: AnalysisResult | None = None) -> None:
        experiment_id = self._experiment_id(observation)
        observed_artifacts: list[str] = []
        for result in observation.tool_results:
            artifact_refs = list(getattr(result, "artifact_refs", []))
            observed_artifacts.extend(artifact_refs)
            metadata = getattr(result, "metadata", {})
            if not isinstance(metadata, Mapping):
                continue
            web = metadata.get("web_observation")
            if isinstance(web, Mapping):
                self._observe_request(web, artifact_refs)
            response_profile = metadata.get("web_response_profile")
            if isinstance(response_profile, Mapping):
                self.knowledge_enhancer.ingest_profile(
                    self.state.application_model,
                    WebResponseProfile.from_dict(response_profile),
                    artifact_refs=artifact_refs,
                    method=str(web.get("method", "GET")) if isinstance(web, Mapping) else "GET",
                )
            for evidence in self.evidence_factory.create_many(
                result,
                experiment_id=experiment_id,
                observation_id=observation.observation_id,
            ):
                if not any(item.evidence_id == evidence.evidence_id for item in self.state.web_evidence):
                    self.state.web_evidence.append(evidence)
        self._synchronize_intelligence(list(dict.fromkeys(observed_artifacts)))
        self._record_experiment(observation)
        if analysis is not None:
            self._record_flag_candidates(analysis, observation)
        self.state.web_evidence = self.state.web_evidence[-100:]
        self.state.web_experiments = self.state.web_experiments[-50:]
        self.state.flag_candidates = self.state.flag_candidates[-20:]
        self.state.application_model.response_profiles = (
            self.state.application_model.response_profiles[-50:]
        )
        self.state.application_model.state_differences = (
            self.state.application_model.state_differences[-50:]
        )
        self.state.application_model.application_behaviors = (
            self.state.application_model.application_behaviors[-100:]
        )

    def verify_flag(self, candidate: Any, accepted: bool | None) -> None:
        value = str(getattr(candidate, "value", ""))
        item = next((entry for entry in self.state.flag_candidates if entry.value == value), None)
        if item is None:
            return
        if accepted is True:
            item.verification_status = WebFlagVerificationStatus.VERIFIED
        elif accepted is False:
            item.verification_status = WebFlagVerificationStatus.REJECTED

    def _observe_request(self, web: Mapping[str, Any], artifact_refs: list[str]) -> None:
        endpoint = str(web.get("endpoint") or "/")
        method = str(web.get("method") or "GET")
        raw_parameters = web.get("parameters", [])
        parameters = [str(item) for item in raw_parameters] if isinstance(raw_parameters, list) else []
        status = web.get("status_code")
        status_code = int(status) if isinstance(status, int) and not isinstance(status, bool) else None
        self.state.application_model.record_endpoint(
            endpoint,
            method=method,
            parameters=parameters,
            status_code=status_code,
            artifact_refs=artifact_refs,
            response_format=str(web.get("response_format", "")),
            content_type=str(web.get("content_type", "")),
            access_states=(
                [str(item) for item in web.get("state_markers", [])]
                if isinstance(web.get("state_markers"), list)
                else []
            ),
            behavior_tags=(
                [str(item) for item in web.get("error_patterns", [])]
                if isinstance(web.get("error_patterns"), list)
                else []
            ),
        )
        locations = web.get("parameter_locations", {})
        shapes = web.get("parameter_shapes", {})
        reflected = {
            str(item) for item in web.get("reflected_parameters", [])
        } if isinstance(web.get("reflected_parameters"), list) else set()
        for name in parameters:
            self.state.application_model.record_parameter_semantics(
                name,
                endpoint=endpoint,
                method=method,
                location=(
                    str(locations.get(name, "request"))
                    if isinstance(locations, Mapping)
                    else "request"
                ),
                semantic_role=self.knowledge_enhancer.semantic_role(name),
                value_shape=(
                    str(shapes.get(name, "unknown"))
                    if isinstance(shapes, Mapping)
                    else "unknown"
                ),
                reflected=name in reflected,
                artifact_refs=artifact_refs,
            )
        for technology in web.get("technologies", []) if isinstance(web.get("technologies"), list) else []:
            self.state.application_model.record_technology(
                str(technology), evidence="HTTP response header", source=str(web.get("request_id", ""))
            )
        session_id = str(web.get("session_id", ""))
        if session_id:
            session = next((item for item in self.state.sessions if item.session_id == session_id), None)
            if session is not None:
                authentication = self.state.application_model.authentication
                authentication.status = session.authentication_status
                authentication.active_session_id = session.session_id
                authentication.evidence_refs = list(dict.fromkeys([
                    *authentication.evidence_refs, *artifact_refs
                ]))

    def _synchronize_intelligence(self, artifact_refs: list[str]) -> None:
        intelligence = self.state.web_intelligence
        self.knowledge_enhancer.synchronize(
            self.state.application_model,
            intelligence,
            artifact_refs=artifact_refs,
        )
        for endpoint in intelligence.attack_surface.endpoints:
            self.state.application_model.record_endpoint(
                endpoint.path,
                method=endpoint.method,
                parameters=list(endpoint.parameters),
                artifact_refs=[item.artifact_id for item in endpoint.artifact_refs],
            )
        for technology in intelligence.technology_evidence:
            self.state.application_model.record_technology(
                technology.technology,
                evidence=technology.evidence,
                source=technology.source,
            )
        existing_behaviors = {item.behavior_id for item in self.state.application_model.response_behaviors}
        for difference in intelligence.response_differences:
            summary = (
                f"status_changed={difference.status_changed}; "
                f"content_changed={difference.content_changed}; "
                f"length_difference={difference.length_difference}; "
                f"title_changed={difference.title_changed}"
            )
            behavior = WebResponseBehavior.create(
                kind="response_comparison",
                endpoint="",
                summary=summary,
                changed=(difference.status_changed or difference.content_changed
                         or difference.title_changed or difference.length_difference != 0),
                baseline_request_id=difference.baseline_request_id,
                current_request_id=difference.current_request_id,
            )
            if behavior.behavior_id not in existing_behaviors:
                self.state.application_model.response_behaviors.append(behavior)
                existing_behaviors.add(behavior.behavior_id)

    def _record_experiment(self, observation: Observation) -> None:
        if observation.proposal.decision_type is not DecisionType.EXPERIMENT_ACTION:
            return
        intent = observation.proposal.metadata.get("experiment", {})
        if not isinstance(intent, Mapping):
            return
        feedback_items = self.state.details.get("experiment_feedback", [])
        feedback = feedback_items[-1] if isinstance(feedback_items, list) and feedback_items else {}
        if not isinstance(feedback, Mapping):
            feedback = {}
        experiment_id = str(feedback.get("experiment_id", ""))
        if not experiment_id:
            return
        try:
            experiment_type = WebExperimentType(
                str(intent.get("experiment_type", WebExperimentType.ENDPOINT_ANALYSIS.value))
            )
        except ValueError:
            experiment_type = WebExperimentType.ENDPOINT_ANALYSIS
        try:
            evidence_type = WebEvidenceType(
                str(intent.get("evidence_type", WebEvidenceType.RESPONSE_BEHAVIOR.value))
            )
        except ValueError:
            evidence_type = WebEvidenceType.RESPONSE_BEHAVIOR
        evidence_ids = [
            item.evidence_id for item in self.state.web_evidence
            if item.experiment_id == experiment_id
        ]
        existing = next((item for item in self.state.web_experiments
                         if item.experiment_id == experiment_id), None)
        if existing is None:
            self.state.web_experiments.append(WebExperimentRecord(
                experiment_id=experiment_id,
                hypothesis_id=str(feedback.get("hypothesis_id") or intent.get("hypothesis_id", "")),
                experiment_type=experiment_type,
                goal=str(intent.get("goal", "")),
                expected_observation=str(intent.get("expected_result", "")),
                evidence_type=evidence_type,
                status="COMPLETED",
                context=(
                    dict(intent.get("context", {}))
                    if isinstance(intent.get("context"), Mapping)
                    else {}
                ),
                evaluation=str(feedback.get("evaluation", "")),
                evidence_ids=evidence_ids,
                experience_influence=[
                    str(item) for item in intent.get("experience_influence", [])
                ] if isinstance(intent.get("experience_influence"), list) else [],
            ))
        else:
            existing.status = "COMPLETED"
            existing.evaluation = str(feedback.get("evaluation", existing.evaluation))
            existing.evidence_ids = list(dict.fromkeys([*existing.evidence_ids, *evidence_ids]))
            existing.updated_at = utc_now_iso()

    def _record_flag_candidates(self, analysis: AnalysisResult, observation: Observation) -> None:
        artifact_refs = list(dict.fromkeys(
            artifact_id for result in observation.tool_results
            for artifact_id in result.artifact_refs
        ))
        for candidate in analysis.flag_candidates:
            existing = next((item for item in self.state.flag_candidates
                             if item.value == candidate.value), None)
            if existing is not None:
                existing.artifact_refs = list(dict.fromkeys([
                    *existing.artifact_refs, *artifact_refs
                ]))
                if existing.artifact_refs:
                    existing.verification_status = WebFlagVerificationStatus.EVIDENCE_BOUND
                continue
            self.state.flag_candidates.append(WebFlagCandidate(
                value=candidate.value,
                source=candidate.source,
                confidence=candidate.confidence,
                evidence_summary=candidate.evidence,
                artifact_refs=artifact_refs,
                verification_status=(
                    WebFlagVerificationStatus.EVIDENCE_BOUND
                    if artifact_refs else WebFlagVerificationStatus.DETECTED
                ),
            ))

    def _experiment_id(self, observation: Observation) -> str:
        if observation.proposal.decision_type is not DecisionType.EXPERIMENT_ACTION:
            return ""
        feedback_items = self.state.details.get("experiment_feedback", [])
        if isinstance(feedback_items, list) and feedback_items and isinstance(feedback_items[-1], Mapping):
            return str(feedback_items[-1].get("experiment_id", ""))
        return ""
