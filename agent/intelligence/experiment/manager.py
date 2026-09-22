"""R6 experiment lifecycle services with no Tool execution capability."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from agent.intelligence.experiment.models import (
    EvidenceRecord,
    Experiment,
    ExperimentStatus,
)
from agent.intelligence.models import (
    ArtifactReference,
    Hypothesis,
    HypothesisSource,
    HypothesisStatus,
    Priority,
)
from agent.intelligence.store import IntelligenceStore


class ExperimentManager:
    """Create and transition hypotheses, experiments, and evidence.

    The manager intentionally receives no Tool registry or executor. Callers
    execute an approved action through ToolRuntime and then record the resulting
    observation here.
    """

    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def create_hypothesis(
        self,
        statement: str,
        domain: str,
        confidence: float = 0.5,
        *,
        source: HypothesisSource = HypothesisSource.MANUAL,
        priority: Priority = Priority.MEDIUM,
        related_artifacts: Iterable[ArtifactReference] = (),
        experience_influence: Iterable[str] = (),
    ) -> Hypothesis:
        return self.store.add_hypothesis(
            Hypothesis(
                statement=statement,
                domain=domain,
                confidence=confidence,
                source=source,
                priority=priority,
                related_artifacts=list(related_artifacts),
                experience_influence=list(
                    dict.fromkeys(
                        str(item) for item in experience_influence if str(item)
                    )
                ),
            )
        )

    def close_hypothesis(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        evidence_refs: Iterable[str],
    ) -> Hypothesis:
        hypothesis = self._hypothesis(hypothesis_id)
        if hypothesis.status is not HypothesisStatus.OPEN:
            raise ValueError("only OPEN hypotheses can be closed")
        if status not in {HypothesisStatus.CONFIRMED, HypothesisStatus.REJECTED}:
            raise ValueError("hypothesis can close only as CONFIRMED or REJECTED")
        references = list(dict.fromkeys(str(item) for item in evidence_refs if str(item)))
        if not references:
            raise ValueError("closing a hypothesis requires evidence")
        for evidence_id in references:
            evidence = self.store.get_evidence(evidence_id)
            if evidence is None or evidence.hypothesis_id != hypothesis_id:
                raise ValueError(f"evidence is not bound to hypothesis: {evidence_id}")
            experiment = self.store.get_experiment(evidence.experiment_id)
            if experiment is None or experiment.status not in {
                ExperimentStatus.SUCCESS,
                ExperimentStatus.FAILED,
            }:
                raise ValueError("hypothesis evidence requires a closed experiment")
        confidence = 1.0 if status is HypothesisStatus.CONFIRMED else 0.0
        return self.store.update_hypothesis(
            hypothesis_id,
            status=status,
            confidence=confidence,
            evidence_refs=references,
        )

    def create_experiment(
        self,
        hypothesis_id: str,
        goal: str,
        action: Mapping[str, Any],
        expected_result: str,
    ) -> Experiment:
        hypothesis = self._hypothesis(hypothesis_id)
        if hypothesis.status is not HypothesisStatus.OPEN:
            raise ValueError("experiments require an OPEN hypothesis")
        return self.store.add_experiment(
            Experiment(
                hypothesis_id=hypothesis_id,
                goal=goal,
                action=dict(action),
                expected_result=expected_result,
            )
        )

    def start_experiment(self, experiment_id: str) -> Experiment:
        experiment = self._experiment(experiment_id)
        if experiment.status is not ExperimentStatus.PROPOSED:
            raise ValueError("only PROPOSED experiments can start")
        experiment.status = ExperimentStatus.RUNNING
        experiment.touch()
        self.store.state.touch()
        return experiment

    def record_result(self, experiment_id: str, actual_result: str) -> Experiment:
        experiment = self._experiment(experiment_id)
        if experiment.status is not ExperimentStatus.RUNNING:
            raise ValueError("results can be recorded only for RUNNING experiments")
        if not isinstance(actual_result, str) or not actual_result.strip():
            raise ValueError("actual_result must be a non-empty string")
        experiment.actual_result = actual_result
        experiment.touch()
        self.store.state.touch()
        return experiment

    def record_evidence(
        self,
        experiment_id: str,
        *,
        source: str,
        observation: str,
        artifact_refs: Iterable[ArtifactReference] = (),
    ) -> EvidenceRecord:
        experiment = self._experiment(experiment_id)
        if experiment.status is not ExperimentStatus.RUNNING:
            raise ValueError("evidence can be recorded only for RUNNING experiments")
        return self.store.add_evidence(
            EvidenceRecord(
                experiment_id=experiment.experiment_id,
                hypothesis_id=experiment.hypothesis_id,
                source=source,
                observation=observation,
                artifact_refs=list(artifact_refs),
            )
        )

    def close_experiment(
        self,
        experiment_id: str,
        status: ExperimentStatus,
    ) -> Experiment:
        experiment = self._experiment(experiment_id)
        if experiment.status is not ExperimentStatus.RUNNING:
            raise ValueError("only RUNNING experiments can be closed")
        if status not in {ExperimentStatus.SUCCESS, ExperimentStatus.FAILED}:
            raise ValueError("experiment can close only as SUCCESS or FAILED")
        if not experiment.actual_result.strip():
            raise ValueError("experiment requires an actual result before closing")
        experiment.status = status
        experiment.touch()
        self.store.state.touch()
        return experiment

    def _hypothesis(self, hypothesis_id: str) -> Hypothesis:
        hypothesis = self.store.get_hypothesis(hypothesis_id)
        if hypothesis is None:
            raise KeyError(hypothesis_id)
        return hypothesis

    def _experiment(self, experiment_id: str) -> Experiment:
        experiment = self.store.get_experiment(experiment_id)
        if experiment is None:
            raise KeyError(experiment_id)
        return experiment


class HypothesisManager:
    """Focused facade for evidence-backed hypothesis lifecycle operations."""

    def __init__(self, manager: ExperimentManager) -> None:
        self.manager = manager

    def create(self, statement: str, domain: str, confidence: float = 0.5) -> Hypothesis:
        return self.manager.create_hypothesis(statement, domain, confidence)

    def close(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        evidence_refs: Iterable[str],
    ) -> Hypothesis:
        return self.manager.close_hypothesis(hypothesis_id, status, evidence_refs)


class ExperimentPlanner:
    """Turn an already reasoned test design into a PROPOSED state record."""

    def __init__(self, manager: ExperimentManager) -> None:
        self.manager = manager

    def propose(
        self,
        hypothesis_id: str,
        goal: str,
        action: Mapping[str, Any],
        expected_result: str,
    ) -> Experiment:
        return self.manager.create_experiment(
            hypothesis_id,
            goal,
            action,
            expected_result,
        )


class ExperimentExecutor:
    """Record lifecycle around execution performed elsewhere by ToolRuntime.

    Despite its architectural name, this class has no method that invokes a
    Tool. It only records that controlled execution started and what result was
    observed.
    """

    def __init__(self, manager: ExperimentManager) -> None:
        self.manager = manager

    def start(self, experiment_id: str) -> Experiment:
        return self.manager.start_experiment(experiment_id)

    def complete(
        self,
        experiment_id: str,
        actual_result: str,
        status: ExperimentStatus,
    ) -> Experiment:
        self.manager.record_result(experiment_id, actual_result)
        return self.manager.close_experiment(experiment_id, status)


class EvidenceCollector:
    """Bind an observed result and optional artifacts to a running experiment."""

    def __init__(self, manager: ExperimentManager) -> None:
        self.manager = manager

    def collect(
        self,
        experiment_id: str,
        *,
        source: str,
        observation: str,
        artifact_refs: Iterable[ArtifactReference] = (),
    ) -> EvidenceRecord:
        return self.manager.record_evidence(
            experiment_id,
            source=source,
            observation=observation,
            artifact_refs=artifact_refs,
        )
