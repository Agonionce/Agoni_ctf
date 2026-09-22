"""Persistent R10.1 experiment execution lifecycle contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping

from agent.intelligence.models import IntelligenceState, utc_now_iso
from agent.intelligence.experiment.runtime.research import (
    ExperimentDecisionRecord,
    HypothesisCandidate,
)


class ExperimentRuntimeStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExperimentEvaluationStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class ExperimentEvaluation:
    experiment_id: str
    status: ExperimentEvaluationStatus
    rationale: str
    evidence_refs: tuple[str, ...]
    evaluated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.experiment_id.strip():
            raise ValueError("evaluation experiment_id must be non-empty")
        if not self.rationale.strip():
            raise ValueError("evaluation rationale must be non-empty")
        if not isinstance(self.status, ExperimentEvaluationStatus):
            raise ValueError("evaluation status is invalid")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "status": self.status.value,
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
            "evaluated_at": self.evaluated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExperimentEvaluation":
        return cls(
            experiment_id=str(data["experiment_id"]),
            status=ExperimentEvaluationStatus(str(data["status"])),
            rationale=str(data["rationale"]),
            evidence_refs=tuple(str(item) for item in _array(data.get("evidence_refs"))),
            evaluated_at=str(data.get("evaluated_at") or utc_now_iso()),
        )


@dataclass
class ExperimentRuntimeRecord:
    run_id: str
    challenge_id: str
    step_id: int
    call_id: str
    hypothesis_id: str
    experiment_id: str
    proposal_fingerprint: str
    proposal: Dict[str, Any]
    status: ExperimentRuntimeStatus = ExperimentRuntimeStatus.CREATED
    observation_id: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    evaluation: ExperimentEvaluation | None = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    feedback_applied: bool = False
    feedback: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "challenge_id",
            "call_id",
            "hypothesis_id",
            "experiment_id",
            "proposal_fingerprint",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"experiment runtime {name} must be non-empty")
        if not isinstance(self.step_id, int) or isinstance(self.step_id, bool) or self.step_id <= 0:
            raise ValueError("experiment runtime step_id must be an integer > 0")
        if not isinstance(self.proposal, dict) or not self.proposal:
            raise ValueError("experiment runtime proposal must be an object")
        if not isinstance(self.status, ExperimentRuntimeStatus):
            raise ValueError("experiment runtime status is invalid")
        if self.feedback_applied and not self.feedback:
            raise ValueError("applied experiment feedback must be persisted")

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "challenge_id": self.challenge_id,
            "step_id": self.step_id,
            "call_id": self.call_id,
            "hypothesis_id": self.hypothesis_id,
            "experiment_id": self.experiment_id,
            "proposal_fingerprint": self.proposal_fingerprint,
            "proposal": self.proposal,
            "status": self.status.value,
            "observation_id": self.observation_id,
            "evidence_ids": list(self.evidence_ids),
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "tool_results": [dict(item) for item in self.tool_results],
            "feedback_applied": self.feedback_applied,
            "feedback": dict(self.feedback),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExperimentRuntimeRecord":
        evaluation = data.get("evaluation")
        return cls(
            run_id=str(data["run_id"]),
            challenge_id=str(data["challenge_id"]),
            step_id=int(data["step_id"]),
            call_id=str(data["call_id"]),
            hypothesis_id=str(data["hypothesis_id"]),
            experiment_id=str(data["experiment_id"]),
            proposal_fingerprint=str(data["proposal_fingerprint"]),
            proposal=dict(_mapping(data.get("proposal"))),
            status=ExperimentRuntimeStatus(str(data["status"])),
            observation_id=str(data.get("observation_id", "")),
            evidence_ids=[str(item) for item in _array(data.get("evidence_ids"))],
            evaluation=(
                ExperimentEvaluation.from_dict(evaluation)
                if isinstance(evaluation, Mapping)
                else None
            ),
            tool_results=[
                dict(item)
                for item in _array(data.get("tool_results"))
                if isinstance(item, Mapping)
            ],
            feedback_applied=bool(data.get("feedback_applied", False)),
            feedback=dict(_mapping(data.get("feedback"))),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )


@dataclass
class ExperimentRuntimeState:
    run_id: str
    challenge_id: str
    records: List[ExperimentRuntimeRecord] = field(default_factory=list)
    active_hypothesis_ids: List[str] = field(default_factory=list)
    active_candidates: List[HypothesisCandidate] = field(default_factory=list)
    follow_up_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    decision_history: List[ExperimentDecisionRecord] = field(default_factory=list)
    last_research_context: Dict[str, Any] = field(default_factory=dict)
    loop_iteration: int = 0
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.challenge_id.strip():
            raise ValueError("experiment runtime state identity must be non-empty")
        self._validate_unique()
        if self.loop_iteration < 0:
            raise ValueError("experiment loop iteration must be non-negative")

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def rebind_run(self, run_id: str) -> None:
        """Attach restored research state to a newly created resumed run."""

        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("experiment runtime run_id must be non-empty")
        self.run_id = run_id
        for record in self.records:
            record.run_id = run_id
            record.touch()
        self.touch()

    def pending(self) -> List[ExperimentRuntimeRecord]:
        return [
            item
            for item in self.records
            if item.status in {
                ExperimentRuntimeStatus.CREATED,
                ExperimentRuntimeStatus.RUNNING,
            }
        ]

    def get(self, experiment_id: str) -> ExperimentRuntimeRecord | None:
        return next(
            (item for item in self.records if item.experiment_id == experiment_id),
            None,
        )

    def for_step(self, step_id: int) -> ExperimentRuntimeRecord | None:
        return next((item for item in self.records if item.step_id == step_id), None)

    def to_dict(self) -> Dict[str, Any]:
        evaluations = {
            item.experiment_id: item.evaluation.to_dict()
            for item in self.records
            if item.evaluation is not None
        }
        return {
            "schema_version": 2,
            "run_id": self.run_id,
            "challenge_id": self.challenge_id,
            "current_experiments": [item.to_dict() for item in self.records],
            "pending_experiments": [item.experiment_id for item in self.pending()],
            "evaluation_results": evaluations,
            "active_hypotheses": list(self.active_hypothesis_ids),
            "hypothesis_candidates": [
                item.to_dict() for item in self.active_candidates
            ],
            "follow_up_suggestions": [
                dict(item) for item in self.follow_up_suggestions
            ],
            "decision_history": [
                item.to_dict() for item in self.decision_history
            ],
            "last_research_context": dict(self.last_research_context),
            "loop_iteration": self.loop_iteration,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExperimentRuntimeState":
        schema_version = data.get("schema_version")
        if schema_version not in {1, 2}:
            raise ValueError("unsupported experiment_runtime.json schema version")
        state = cls(
            run_id=str(data["run_id"]),
            challenge_id=str(data["challenge_id"]),
            records=[
                ExperimentRuntimeRecord.from_dict(item)
                for item in _array(data.get("current_experiments"))
                if isinstance(item, Mapping)
            ],
            active_hypothesis_ids=(
                [str(item) for item in _array(data.get("active_hypotheses"))]
                if schema_version == 2
                else []
            ),
            active_candidates=(
                [
                    HypothesisCandidate.from_dict(item)
                    for item in _array(data.get("hypothesis_candidates"))
                    if isinstance(item, Mapping)
                ]
                if schema_version == 2
                else []
            ),
            follow_up_suggestions=(
                [
                    dict(item)
                    for item in _array(data.get("follow_up_suggestions"))
                    if isinstance(item, Mapping)
                ]
                if schema_version == 2
                else []
            ),
            decision_history=(
                [
                    ExperimentDecisionRecord.from_dict(item)
                    for item in _array(data.get("decision_history"))
                    if isinstance(item, Mapping)
                ]
                if schema_version == 2
                else []
            ),
            last_research_context=(
                dict(_mapping(data.get("last_research_context")))
                if schema_version == 2
                else {}
            ),
            loop_iteration=(
                int(data.get("loop_iteration", 0)) if schema_version == 2 else 0
            ),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )
        pending = [str(item) for item in _array(data.get("pending_experiments"))]
        if pending != [item.experiment_id for item in state.pending()]:
            raise ValueError("experiment runtime pending index is inconsistent")
        raw_evaluations = data.get("evaluation_results", {})
        expected = {
            item.experiment_id: item.evaluation.to_dict()
            for item in state.records
            if item.evaluation is not None
        }
        if not isinstance(raw_evaluations, Mapping) or dict(raw_evaluations) != expected:
            raise ValueError("experiment runtime evaluation index is inconsistent")
        return state

    def validate_against(self, intelligence: IntelligenceState) -> None:
        hypothesis_ids = {item.id for item in intelligence.hypotheses}
        experiments = {
            item.experiment_id: item for item in intelligence.experiments
        }
        evidence = {item.evidence_id: item for item in intelligence.evidence}
        if any(item not in hypothesis_ids for item in self.active_hypothesis_ids):
            raise ValueError("experiment loop references an unknown active hypothesis")
        if any(
            item.hypothesis_id and item.hypothesis_id not in hypothesis_ids
            for item in self.active_candidates
        ):
            raise ValueError("experiment candidate references an unknown hypothesis")
        if any(
            item.hypothesis_id and item.hypothesis_id not in hypothesis_ids
            for item in self.decision_history
        ):
            raise ValueError("experiment decision references an unknown hypothesis")
        for record in self.records:
            if record.run_id != self.run_id or record.challenge_id != self.challenge_id:
                raise ValueError("experiment runtime record identity is inconsistent")
            if record.hypothesis_id not in hypothesis_ids:
                raise ValueError("experiment runtime references an unknown hypothesis")
            experiment = experiments.get(record.experiment_id)
            if experiment is None:
                raise ValueError("experiment runtime references an unknown experiment")
            if experiment.hypothesis_id != record.hypothesis_id:
                raise ValueError("experiment runtime hypothesis binding is inconsistent")
            for evidence_id in record.evidence_ids:
                item = evidence.get(evidence_id)
                if item is None:
                    raise ValueError("experiment runtime references unknown evidence")
                if (
                    item.experiment_id != record.experiment_id
                    or item.hypothesis_id != record.hypothesis_id
                    or item.observation_id != record.observation_id
                    or not item.artifact_refs
                ):
                    raise ValueError(
                        "experiment runtime evidence provenance is inconsistent"
                    )
            if record.evaluation is not None and (
                record.evaluation.experiment_id != record.experiment_id
                or list(record.evaluation.evidence_refs) != record.evidence_ids
            ):
                raise ValueError("experiment runtime evaluation provenance is inconsistent")
            if record.status is ExperimentRuntimeStatus.RUNNING and (
                experiment.status.value != "RUNNING"
                or record.evaluation is not None
                or record.evidence_ids
            ):
                raise ValueError("running experiment runtime state is inconsistent")
            if record.status is ExperimentRuntimeStatus.COMPLETED and (
                experiment.status.value != "SUCCESS"
                or record.evaluation is None
                or not record.evidence_ids
                or not record.tool_results
                or not record.observation_id
            ):
                raise ValueError("completed experiment runtime state is inconsistent")
            if record.status is ExperimentRuntimeStatus.FAILED and (
                experiment.status.value != "FAILED"
                or record.evaluation is None
                or not record.tool_results
                or not record.observation_id
            ):
                raise ValueError("failed experiment runtime state is inconsistent")

    def _validate_unique(self) -> None:
        experiment_ids = [item.experiment_id for item in self.records]
        step_ids = [item.step_id for item in self.records]
        if len(experiment_ids) != len(set(experiment_ids)):
            raise ValueError("duplicate experiment runtime id")
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("duplicate experiment runtime step")
        if len(self.active_hypothesis_ids) != len(set(self.active_hypothesis_ids)):
            raise ValueError("duplicate active experiment-loop hypothesis")
        candidate_ids = [item.candidate_id for item in self.active_candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("duplicate experiment-loop candidate")
        decision_steps = [item.source_step for item in self.decision_history]
        if len(decision_steps) != len(set(decision_steps)):
            raise ValueError("duplicate experiment-loop decision step")


class ExperimentRuntimeManager:
    """Transition persistent runtime records without executing a Tool."""

    def __init__(self, state: ExperimentRuntimeState) -> None:
        self.state = state

    def create(
        self,
        *,
        step_id: int,
        call_id: str,
        hypothesis_id: str,
        experiment_id: str,
        proposal_fingerprint: str,
        proposal: Mapping[str, Any],
    ) -> ExperimentRuntimeRecord:
        if self.state.for_step(step_id) is not None:
            raise ValueError("experiment runtime step already exists")
        if self.state.get(experiment_id) is not None:
            raise ValueError("experiment runtime id already exists")
        record = ExperimentRuntimeRecord(
            run_id=self.state.run_id,
            challenge_id=self.state.challenge_id,
            step_id=step_id,
            call_id=call_id,
            hypothesis_id=hypothesis_id,
            experiment_id=experiment_id,
            proposal_fingerprint=proposal_fingerprint,
            proposal=dict(proposal),
        )
        self.state.records.append(record)
        self.state.touch()
        return record

    def start(self, experiment_id: str) -> ExperimentRuntimeRecord:
        record = self._record(experiment_id)
        if record.status is not ExperimentRuntimeStatus.CREATED:
            raise ValueError("only CREATED experiment runtime records can start")
        record.status = ExperimentRuntimeStatus.RUNNING
        record.touch()
        self.state.touch()
        return record

    def finish(
        self,
        experiment_id: str,
        *,
        successful: bool,
        observation_id: str,
        evidence_ids: Iterable[str],
        evaluation: ExperimentEvaluation,
        tool_results: Iterable[Mapping[str, Any]],
    ) -> ExperimentRuntimeRecord:
        record = self._record(experiment_id)
        if record.status is not ExperimentRuntimeStatus.RUNNING:
            raise ValueError("only RUNNING experiment runtime records can finish")
        if not observation_id.strip():
            raise ValueError("completed experiment runtime requires observation provenance")
        references = list(dict.fromkeys(str(item) for item in evidence_ids if str(item)))
        if list(evaluation.evidence_refs) != references:
            raise ValueError("evaluation evidence does not match the runtime record")
        record.status = (
            ExperimentRuntimeStatus.COMPLETED
            if successful
            else ExperimentRuntimeStatus.FAILED
        )
        record.observation_id = observation_id
        record.evidence_ids = references
        record.evaluation = evaluation
        record.tool_results = [dict(item) for item in tool_results]
        record.touch()
        self.state.touch()
        return record

    def record_feedback(
        self,
        experiment_id: str,
        feedback: Mapping[str, Any],
    ) -> ExperimentRuntimeRecord:
        record = self._record(experiment_id)
        if record.evaluation is None:
            raise ValueError("feedback requires a completed evaluation")
        if record.feedback_applied:
            return record
        if str(feedback.get("experiment_id", "")) != record.experiment_id:
            raise ValueError("feedback belongs to a different experiment")
        if str(feedback.get("hypothesis_id", "")) != record.hypothesis_id:
            raise ValueError("feedback belongs to a different hypothesis")
        record.feedback = dict(feedback)
        record.feedback_applied = True
        record.touch()
        self.state.touch()
        return record

    def _record(self, experiment_id: str) -> ExperimentRuntimeRecord:
        record = self.state.get(experiment_id)
        if record is None:
            raise KeyError(experiment_id)
        return record


def _array(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
