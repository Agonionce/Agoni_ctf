"""Translate Analyzer suggestions into audited IntelligenceStore mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from agent.intelligence.models import (
    ArtifactReference,
    AttackSurface,
    Confidence,
    Credential,
    CredentialStatus,
    EndpointFinding,
    Fact,
    FailedAttempt,
    Finding,
    Hypothesis,
    HypothesisSource,
    HypothesisStatus,
    KnowledgeUpdateSuggestion,
    OpenQuestion,
    OpenQuestionStatus,
    Priority,
    artifact_references,
    enum_from,
)
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import AnalysisResult, Observation


@dataclass
class KnowledgeUpdateResult:
    applied_ids: List[str] = field(default_factory=list)
    rejected: List[str] = field(default_factory=list)


class KnowledgeUpdater:
    """Own state writes after an Analyzer has returned typed suggestions."""

    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def apply(
        self,
        analysis: AnalysisResult,
        observation: Observation,
    ) -> KnowledgeUpdateResult:
        result = KnowledgeUpdateResult()
        for suggestion in analysis.knowledge_updates:
            try:
                item_id = self._apply_suggestion(suggestion, observation.step_id)
                result.applied_ids.append(item_id)
            except (KeyError, TypeError, ValueError) as error:
                result.rejected.append(f"{suggestion.kind}: {error}")
        return result

    def _apply_suggestion(
        self,
        suggestion: KnowledgeUpdateSuggestion,
        observation_step: int,
    ) -> str:
        if suggestion.operation == "update":
            return self._update(suggestion)

        payload = dict(suggestion.payload)
        source_step = suggestion.source_step if suggestion.source_step is not None else observation_step
        references = suggestion.artifact_refs
        kind = suggestion.kind
        if kind == "fact":
            return self.store.add_fact(
                Fact(
                    category=self._required(payload, "category"),
                    content=self._required(payload, "content"),
                    confidence=enum_from(payload.get("confidence"), Confidence, Confidence.MEDIUM),
                    source_step=source_step,
                    artifact_refs=references,
                )
            ).id
        if kind == "hypothesis":
            status = enum_from(
                payload.get("status"),
                HypothesisStatus,
                HypothesisStatus.OPEN,
            )
            if status in {HypothesisStatus.CONFIRMED, HypothesisStatus.REJECTED}:
                raise ValueError(
                    "terminal hypothesis status requires the experiment evidence lifecycle"
                )
            return self.store.add_hypothesis(
                Hypothesis(
                    statement=self._required(payload, "statement"),
                    status=status,
                    confidence=self._hypothesis_confidence(payload.get("confidence")),
                    supporting_facts=self._string_list(payload.get("supporting_facts")),
                    contradicting_facts=self._string_list(payload.get("contradicting_facts")),
                    domain=str(payload.get("domain") or "misc"),
                    evidence_refs=self._string_list(payload.get("evidence_refs")),
                    source=enum_from(
                        payload.get("source"),
                        HypothesisSource,
                        HypothesisSource.ANALYZER,
                    ),
                    priority=enum_from(
                        payload.get("priority"), Priority, Priority.MEDIUM
                    ),
                    related_artifacts=(
                        artifact_references(payload.get("related_artifacts"))
                        or list(references)
                    ),
                    experience_influence=self._string_list(
                        payload.get("experience_influence")
                    ),
                )
            ).id
        if kind == "failed_attempt":
            return self.store.add_failed_attempt(
                FailedAttempt(
                    category=self._required(payload, "category"),
                    target=str(payload.get("target", "")),
                    method=self._required(payload, "method"),
                    input_payload=str(payload.get("input_payload", "")),
                    result=str(payload.get("result", "failed")),
                    reason=str(payload.get("reason", "")),
                    source_step=source_step,
                    artifact_refs=references,
                )
            ).id
        if kind == "finding":
            return self.store.add_finding(
                Finding(
                    title=self._required(payload, "title"),
                    description=self._required(payload, "description"),
                    importance=enum_from(payload.get("importance"), Priority, Priority.MEDIUM),
                    related_facts=self._string_list(payload.get("related_facts")),
                    related_artifacts=references,
                    source_steps=[source_step],
                )
            ).id
        if kind == "credential":
            return self.store.add_credential(
                Credential(
                    credential_type=self._required(payload, "credential_type"),
                    value=self._required(payload, "value"),
                    location=str(payload.get("location", "")),
                    status=enum_from(
                        payload.get("status"), CredentialStatus, CredentialStatus.UNKNOWN
                    ),
                    source=str(payload.get("source", f"step-{source_step}")),
                )
            ).id
        if kind == "attack_surface":
            details = payload.get("details", {})
            return self.store.add_attack_surface(
                AttackSurface(
                    category=self._required(payload, "category"),
                    target=self._required(payload, "target"),
                    method=str(payload.get("method", "")),
                    parameters=self._string_list(payload.get("parameters")),
                    details=dict(details) if isinstance(details, dict) else {},
                    source_step=source_step,
                    artifact_refs=references,
                )
            ).id
        if kind == "endpoint_finding":
            return self.store.add_endpoint_finding(
                EndpointFinding(
                    path=self._required(payload, "path"),
                    method=str(payload.get("method", "GET")),
                    parameters=self._string_list(payload.get("parameters")),
                    source=str(payload.get("source", "web intelligence")),
                    confidence=enum_from(
                        payload.get("confidence"),
                        Confidence,
                        Confidence.MEDIUM,
                    ),
                    source_step=source_step,
                    artifact_refs=references,
                )
            ).id
        if kind == "open_question":
            return self.store.add_open_question(
                OpenQuestion(
                    question=self._required(payload, "question"),
                    priority=enum_from(payload.get("priority"), Priority, Priority.MEDIUM),
                    status=enum_from(
                        payload.get("status"), OpenQuestionStatus, OpenQuestionStatus.OPEN
                    ),
                    related_findings=self._string_list(payload.get("related_findings")),
                )
            ).id
        raise ValueError(f"unsupported knowledge update kind: {kind}")

    def _update(self, suggestion: KnowledgeUpdateSuggestion) -> str:
        payload = dict(suggestion.payload)
        item_id = self._required(payload, "id")
        changes = {key: value for key, value in payload.items() if key != "id"}
        if suggestion.kind == "fact" and "confidence" in changes:
            changes["confidence"] = enum_from(changes["confidence"], Confidence, Confidence.MEDIUM)
        if suggestion.kind == "hypothesis":
            if "status" in changes:
                changes["status"] = enum_from(
                    changes["status"], HypothesisStatus, HypothesisStatus.OPEN
                )
            if "confidence" in changes:
                changes["confidence"] = self._hypothesis_confidence(
                    changes["confidence"]
                )
            if "source" in changes:
                changes["source"] = enum_from(
                    changes["source"],
                    HypothesisSource,
                    HypothesisSource.ANALYZER,
                )
            if "priority" in changes:
                changes["priority"] = enum_from(
                    changes["priority"], Priority, Priority.MEDIUM
                )
            if "related_artifacts" in changes:
                changes["related_artifacts"] = artifact_references(
                    changes["related_artifacts"]
                )
            terminal_status = changes.get("status")
            if terminal_status in {
                HypothesisStatus.CONFIRMED,
                HypothesisStatus.REJECTED,
            }:
                from agent.intelligence.experiment.manager import ExperimentManager

                hypothesis = self.store.get_hypothesis(item_id)
                if hypothesis is None:
                    raise KeyError(item_id)
                references = self._string_list(
                    changes.pop("evidence_refs", hypothesis.evidence_refs)
                )
                changes.pop("status")
                changes.pop("confidence", None)
                if changes:
                    self.store.update_hypothesis(item_id, **changes)
                ExperimentManager(self.store).close_hypothesis(
                    item_id,
                    terminal_status,
                    references,
                )
                return item_id
        if suggestion.kind == "finding" and "importance" in changes:
            changes["importance"] = enum_from(changes["importance"], Priority, Priority.MEDIUM)
        if suggestion.kind == "credential" and "status" in changes:
            changes["status"] = enum_from(
                changes["status"], CredentialStatus, CredentialStatus.UNKNOWN
            )
        if suggestion.kind == "open_question":
            if "priority" in changes:
                changes["priority"] = enum_from(changes["priority"], Priority, Priority.MEDIUM)
            if "status" in changes:
                changes["status"] = enum_from(
                    changes["status"], OpenQuestionStatus, OpenQuestionStatus.OPEN
                )
        if suggestion.kind == "endpoint_finding" and "confidence" in changes:
            changes["confidence"] = enum_from(
                changes["confidence"], Confidence, Confidence.MEDIUM
            )
        method = {
            "fact": self.store.update_fact,
            "hypothesis": self.store.update_hypothesis,
            "failed_attempt": self.store.update_failed_attempt,
            "finding": self.store.update_finding,
            "credential": self.store.update_credential,
            "attack_surface": self.store.update_attack_surface,
            "endpoint_finding": self.store.update_endpoint_finding,
            "open_question": self.store.update_open_question,
        }.get(suggestion.kind)
        if method is None:
            raise ValueError(f"unsupported knowledge update kind: {suggestion.kind}")
        method(item_id, **changes)
        return item_id

    @staticmethod
    def _required(payload: dict, field_name: str) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"missing {field_name}")
        return value

    @staticmethod
    def _string_list(value: object) -> List[str]:
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _hypothesis_confidence(value: object) -> Confidence | float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            confidence = float(value)
            if not 0 <= confidence <= 1:
                raise ValueError("hypothesis confidence must be in [0, 1]")
            return confidence
        return enum_from(value, Confidence, Confidence.LOW)
