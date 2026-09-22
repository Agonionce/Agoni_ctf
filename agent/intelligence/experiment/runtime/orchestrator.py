"""Decision routing around ToolRuntime for R10.1 experiment actions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Sequence

from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.models import EvidenceRecord, ExperimentStatus
from agent.intelligence.experiment.runtime.evaluator import (
    EvidenceFactory,
    EvidenceProvenanceError,
    ExperimentEvaluator,
)
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluation,
    ExperimentEvaluationStatus,
    ExperimentRuntimeManager,
    ExperimentRuntimeRecord,
    ExperimentRuntimeState,
    ExperimentRuntimeStatus,
)
from agent.intelligence.models import HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import (
    ActionProposal,
    DecisionType,
    Observation,
    ToolCall,
    ToolResult,
    to_jsonable,
)


class ExperimentOrchestrator:
    """Bind experiment reasoning state to controlled execution results.

    The orchestrator does not own an Executor or Tool registry. AgentRuntime
    continues to execute the unchanged ActionProposal through its injected
    Executor, then supplies the resulting Observation here.
    """

    def __init__(
        self,
        intelligence_store: IntelligenceStore,
        runtime_state: ExperimentRuntimeState,
        *,
        evidence_factory: EvidenceFactory | None = None,
        evaluator: ExperimentEvaluator | None = None,
        autonomous_loop: Any = None,
    ) -> None:
        if intelligence_store.state.challenge_id != runtime_state.challenge_id:
            raise ValueError("experiment runtime belongs to a different challenge")
        self.intelligence_store = intelligence_store
        self.experiment_manager = ExperimentManager(intelligence_store)
        self.runtime_manager = ExperimentRuntimeManager(runtime_state)
        self.evidence_factory = evidence_factory or EvidenceFactory()
        self.evaluator = evaluator or ExperimentEvaluator()
        self.autonomous_loop = autonomous_loop

    @property
    def state(self) -> ExperimentRuntimeState:
        return self.runtime_manager.state

    @staticmethod
    def handles(proposal: ActionProposal) -> bool:
        return proposal.decision_type is DecisionType.EXPERIMENT_ACTION

    def prepare(
        self,
        proposal: ActionProposal,
        *,
        step_id: int,
        run_id: str,
        challenge_id: str,
    ) -> ExperimentRuntimeRecord | None:
        if not self.handles(proposal):
            return None
        if run_id != self.state.run_id or challenge_id != self.state.challenge_id:
            raise ValueError("experiment proposal belongs to a different run")
        fingerprint = self._proposal_fingerprint(proposal)
        existing = self.state.for_step(step_id)
        if existing is not None:
            if existing.proposal_fingerprint != fingerprint:
                raise ValueError(
                    "checkpointed experiment proposal differs from the resumed proposal"
                )
            return existing

        intent = self._intent(proposal)
        hypothesis_id = str(intent.get("hypothesis_id", "")).strip()
        if hypothesis_id:
            hypothesis = self.intelligence_store.get_hypothesis(hypothesis_id)
            if hypothesis is None:
                raise ValueError("experiment references an unknown hypothesis")
            if hypothesis.status is not HypothesisStatus.OPEN:
                raise ValueError("experiment requires an OPEN hypothesis")
        else:
            hypothesis = self.experiment_manager.create_hypothesis(
                str(intent["hypothesis_statement"]),
                str(intent.get("hypothesis_domain") or "misc"),
                float(intent.get("hypothesis_confidence", 0.5)),
            )
        action = proposal.actions[0]
        experiment = self.experiment_manager.create_experiment(
            hypothesis.id,
            str(intent["goal"]),
            {
                "tool_name": action.tool_name,
                "arguments": dict(action.arguments),
            },
            str(intent["expected_result"]),
        )
        record = self.runtime_manager.create(
            step_id=step_id,
            call_id=action.call_id,
            hypothesis_id=hypothesis.id,
            experiment_id=experiment.experiment_id,
            proposal_fingerprint=fingerprint,
            proposal=self._proposal_snapshot(proposal),
        )
        self.experiment_manager.start_experiment(experiment.experiment_id)
        return self.runtime_manager.start(record.experiment_id)

    def complete(
        self,
        proposal: ActionProposal,
        observation: Observation,
    ) -> ExperimentEvaluation | None:
        if not self.handles(proposal):
            return None
        record = self.state.for_step(observation.step_id)
        if record is None:
            raise ValueError("experiment runtime record is missing")
        if record.proposal_fingerprint != self._proposal_fingerprint(proposal):
            raise ValueError("experiment observation does not match its proposal")
        if record.status in {
            ExperimentRuntimeStatus.COMPLETED,
            ExperimentRuntimeStatus.FAILED,
        }:
            if record.evaluation is None:
                raise ValueError("terminal experiment runtime has no evaluation")
            if record.observation_id != observation.observation_id:
                raise ValueError("terminal experiment observation provenance changed")
            self._apply_feedback(record, record.evaluation)
            return record.evaluation
        if record.status is not ExperimentRuntimeStatus.RUNNING:
            raise ValueError("experiment runtime is not RUNNING")

        experiment = self.intelligence_store.get_experiment(record.experiment_id)
        if experiment is None:
            raise ValueError("experiment intelligence record is missing")
        evidence: list[EvidenceRecord] = []
        provenance_errors: list[str] = []
        for result in observation.tool_results:
            try:
                item = self.evidence_factory.create(
                    result,
                    experiment_id=record.experiment_id,
                    hypothesis_id=record.hypothesis_id,
                    observation_id=observation.observation_id,
                )
            except EvidenceProvenanceError as error:
                provenance_errors.append(str(error))
                continue
            evidence.append(self.intelligence_store.add_evidence(item))

        actual_result = self._actual_result(observation.tool_results, provenance_errors)
        self.experiment_manager.record_result(record.experiment_id, actual_result)
        execution_success = bool(observation.tool_results) and all(
            result.success for result in observation.tool_results
        )
        evidence_complete = bool(evidence) and not provenance_errors
        evaluation = self.evaluator.evaluate(
            experiment,
            evidence,
            observation.tool_results,
        )
        self.experiment_manager.close_experiment(
            record.experiment_id,
            ExperimentStatus.SUCCESS
            if evaluation.status is ExperimentEvaluationStatus.SUPPORTED
            else ExperimentStatus.FAILED,
        )
        if evidence:
            hypothesis = self.intelligence_store.get_hypothesis(record.hypothesis_id)
            if hypothesis is None:
                raise ValueError("experiment hypothesis record is missing")
            references = list(
                dict.fromkeys(
                    [
                        *hypothesis.evidence_refs,
                        *(item.evidence_id for item in evidence),
                    ]
                )
            )
            self.intelligence_store.update_hypothesis(
                hypothesis.id,
                evidence_refs=references,
            )
        record = self.runtime_manager.finish(
            record.experiment_id,
            successful=(
                execution_success
                and evidence_complete
                and evaluation.status is ExperimentEvaluationStatus.SUPPORTED
            ),
            observation_id=observation.observation_id,
            evidence_ids=[item.evidence_id for item in evidence],
            evaluation=evaluation,
            tool_results=[self._tool_result_snapshot(item) for item in observation.tool_results],
        )
        self._apply_feedback(record, evaluation)
        return evaluation

    def advance_loop(
        self,
        observation: Observation,
        analysis: Any,
    ) -> Any:
        if self.autonomous_loop is None:
            return None
        return self.autonomous_loop.advance(observation, analysis)

    def _apply_feedback(
        self,
        record: ExperimentRuntimeRecord,
        evaluation: ExperimentEvaluation,
    ) -> None:
        if self.autonomous_loop is None or record.feedback_applied:
            return
        feedback = self.autonomous_loop.apply_feedback(record, evaluation)
        self.runtime_manager.record_feedback(
            record.experiment_id,
            feedback.to_dict(),
        )

    def pending_proposal(self, step_id: int) -> ActionProposal | None:
        record = self.state.for_step(step_id)
        if record is None:
            return None
        return self._proposal_from_snapshot(record.proposal)

    def restored_tool_results(self, step_id: int) -> list[ToolResult]:
        record = self.state.for_step(step_id)
        if record is None or record.status not in {
            ExperimentRuntimeStatus.COMPLETED,
            ExperimentRuntimeStatus.FAILED,
        }:
            return []
        if not record.tool_results:
            raise ValueError("completed experiment has no recoverable ToolResult")
        return [self._tool_result_from_snapshot(item) for item in record.tool_results]

    def record_for_step(self, step_id: int) -> ExperimentRuntimeRecord | None:
        return self.state.for_step(step_id)

    @staticmethod
    def _intent(proposal: ActionProposal) -> Mapping[str, Any]:
        raw = proposal.metadata.get("experiment")
        if not isinstance(raw, Mapping):
            raise ValueError("experiment proposal metadata is missing")
        return raw

    @staticmethod
    def _actual_result(
        results: Sequence[ToolResult],
        provenance_errors: Sequence[str],
    ) -> str:
        summaries = []
        for result in results:
            detail = result.stdout or result.stderr or result.error or "no textual output"
            summaries.append(
                f"{result.tool_name}:{result.call_id}:success={result.success}:{detail[:4000]}"
            )
        summaries.extend(f"provenance_error:{item}" for item in provenance_errors)
        return " | ".join(summaries) or "experiment produced no ToolResult"

    @staticmethod
    def _proposal_fingerprint(proposal: ActionProposal) -> str:
        payload = json.dumps(
            to_jsonable(proposal),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _proposal_snapshot(proposal: ActionProposal) -> Dict[str, Any]:
        snapshot = to_jsonable(proposal)
        if not isinstance(snapshot, dict):
            raise ValueError("experiment proposal could not be serialized")
        return snapshot

    @staticmethod
    def _proposal_from_snapshot(data: Mapping[str, Any]) -> ActionProposal:
        return ActionProposal(
            objective=str(data["objective"]),
            reasoning_summary=str(data["reasoning_summary"]),
            actions=[
                ToolCall(
                    call_id=str(item["call_id"]),
                    tool_name=str(item["tool_name"]),
                    arguments=dict(item.get("arguments", {})),
                    metadata=dict(item.get("metadata", {})),
                )
                for item in data.get("actions", [])
                if isinstance(item, Mapping)
            ],
            metadata=dict(data.get("metadata", {})),
            decision_type=str(data.get("decision_type", "normal_action")),
        )

    @staticmethod
    def _tool_result_snapshot(result: ToolResult) -> Dict[str, Any]:
        snapshot = to_jsonable(result)
        if not isinstance(snapshot, dict):
            raise ValueError("ToolResult could not be serialized")
        return snapshot

    @staticmethod
    def _tool_result_from_snapshot(data: Mapping[str, Any]) -> ToolResult:
        return ToolResult(
            call_id=str(data["call_id"]),
            tool_name=str(data["tool_name"]),
            success=bool(data["success"]),
            exit_code=data.get("exit_code"),
            stdout=str(data.get("stdout", "")),
            stderr=str(data.get("stderr", "")),
            error=str(data["error"]) if data.get("error") is not None else None,
            started_at=_datetime(data.get("started_at")),
            finished_at=_datetime(data.get("finished_at")),
            duration=float(data.get("duration", 0.0)),
            metadata=dict(data.get("metadata", {})),
            artifact_refs=[str(item) for item in data.get("artifact_refs", [])],
            execution_context=dict(data.get("execution_context", {})),
            policy_decision=(
                dict(data["policy_decision"])
                if isinstance(data.get("policy_decision"), Mapping)
                else None
            ),
            tool_error=(
                dict(data["tool_error"])
                if isinstance(data.get("tool_error"), Mapping)
                else None
            ),
        )


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
