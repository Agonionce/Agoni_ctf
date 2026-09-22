"""Evidence-driven R10.2 feedback with no execution capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent.domains.manager import DomainRuntimeManager
from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluation,
    ExperimentEvaluationStatus,
    ExperimentRuntimeRecord,
)
from agent.intelligence.experiment.runtime.research import DomainExperimentAdapter
from agent.intelligence.models import (
    ArtifactReference,
    FailedAttempt,
    HypothesisStatus,
)
from agent.intelligence.store import IntelligenceStore


@dataclass(frozen=True)
class ExperimentFeedback:
    experiment_id: str
    hypothesis_id: str
    evaluation: ExperimentEvaluationStatus
    hypothesis_status: HypothesisStatus
    confidence_before: float
    confidence_after: float
    failed_attempt_id: str = ""
    next_experiment_goal: str = ""
    domain_context_updated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "hypothesis_id": self.hypothesis_id,
            "evaluation": self.evaluation.value,
            "hypothesis_status": self.hypothesis_status.value,
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "failed_attempt_id": self.failed_attempt_id,
            "next_experiment_goal": self.next_experiment_goal,
            "domain_context_updated": self.domain_context_updated,
        }


class ExperimentFeedbackManager:
    """Apply evaluator output to Intelligence and bounded Domain state."""

    def __init__(
        self,
        store: IntelligenceStore,
        *,
        domain_manager: DomainRuntimeManager | None = None,
        domain_adapter: DomainExperimentAdapter | None = None,
    ) -> None:
        self.store = store
        self.experiment_manager = ExperimentManager(store)
        self.domain_manager = domain_manager
        self.domain_adapter = domain_adapter or DomainExperimentAdapter()

    def apply(
        self,
        record: ExperimentRuntimeRecord,
        evaluation: ExperimentEvaluation,
    ) -> ExperimentFeedback:
        hypothesis = self.store.get_hypothesis(record.hypothesis_id)
        experiment = self.store.get_experiment(record.experiment_id)
        if hypothesis is None or experiment is None:
            raise ValueError("feedback references missing experiment intelligence")
        self._validate_evidence(record, evaluation)
        before = _numeric_confidence(hypothesis.confidence)
        failed_attempt_id = ""
        next_goal = ""
        if evaluation.status is ExperimentEvaluationStatus.SUPPORTED:
            updated = self.store.update_hypothesis(
                hypothesis.id,
                status=HypothesisStatus.SUPPORTED,
                confidence=min(0.95, before + 0.2),
            )
        elif evaluation.status is ExperimentEvaluationStatus.CONTRADICTED:
            updated = self.experiment_manager.close_hypothesis(
                hypothesis.id,
                HypothesisStatus.REJECTED,
                evaluation.evidence_refs,
            )
            existing = next(
                (
                    item
                    for item in self.store.state.failed_attempts
                    if item.target == hypothesis.id
                    and item.method == "controlled experiment evaluation"
                ),
                None,
            )
            if existing is None:
                references = self._artifact_references(evaluation.evidence_refs)
                existing = self.store.add_failed_attempt(
                    FailedAttempt(
                        category="experiment_contradicted",
                        target=hypothesis.id,
                        method="controlled experiment evaluation",
                        input_payload="",
                        result="CONTRADICTED",
                        reason=evaluation.rationale,
                        source_step=record.step_id,
                        artifact_refs=references,
                    )
                )
            failed_attempt_id = existing.id
        else:
            next_goal = (
                f"refine {experiment.goal} with a distinct observable and preserve provenance"
            )
            updated = self.store.update_hypothesis(
                hypothesis.id,
                status=HypothesisStatus.OPEN,
                confidence=max(0.05, before - 0.05),
            )
        feedback_payload: dict[str, Any] = {
            "experiment_id": record.experiment_id,
            "hypothesis_id": record.hypothesis_id,
            "evaluation": evaluation.status.value,
            "evidence_count": len(evaluation.evidence_refs),
            "evidence_refs": list(evaluation.evidence_refs),
            "next_experiment_goal": next_goal,
        }
        domain_updated = self.domain_adapter.apply_feedback(
            self.domain_manager,
            feedback_payload,
        )
        return ExperimentFeedback(
            experiment_id=record.experiment_id,
            hypothesis_id=record.hypothesis_id,
            evaluation=evaluation.status,
            hypothesis_status=updated.status,
            confidence_before=before,
            confidence_after=_numeric_confidence(updated.confidence),
            failed_attempt_id=failed_attempt_id,
            next_experiment_goal=next_goal,
            domain_context_updated=domain_updated,
        )

    def _validate_evidence(
        self,
        record: ExperimentRuntimeRecord,
        evaluation: ExperimentEvaluation,
    ) -> None:
        if evaluation.status in {
            ExperimentEvaluationStatus.SUPPORTED,
            ExperimentEvaluationStatus.CONTRADICTED,
        } and not evaluation.evidence_refs:
            raise ValueError("decisive feedback requires evidence")
        for evidence_id in evaluation.evidence_refs:
            evidence = self.store.get_evidence(evidence_id)
            if evidence is None or (
                evidence.experiment_id != record.experiment_id
                or evidence.hypothesis_id != record.hypothesis_id
                or not evidence.artifact_refs
            ):
                raise ValueError("feedback evidence provenance is inconsistent")

    def _artifact_references(
        self,
        evidence_ids: tuple[str, ...],
    ) -> list[ArtifactReference]:
        references: list[ArtifactReference] = []
        for evidence_id in evidence_ids:
            evidence = self.store.get_evidence(evidence_id)
            if evidence is not None:
                references.extend(evidence.artifact_refs)
        return list(dict.fromkeys(references))


def _numeric_confidence(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return {
        "LOW": 0.25,
        "MEDIUM": 0.5,
        "HIGH": 0.75,
        "CONFIRMED": 1.0,
    }.get(str(getattr(value, "value", value)).upper(), 0.5)
