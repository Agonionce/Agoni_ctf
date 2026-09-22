"""Checkpoint format for intelligence, R6 experiments, and domain state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping

from agent.domains.base.runtime import DomainRuntimeState
from agent.intelligence.models import IntelligenceState, KnowledgeUpdateSuggestion
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentRuntimeState,
)
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    FlagCandidateKind,
    Observation,
    RunCounters,
    RunState,
    RunStatus,
    StepRecord,
    TerminationDecision,
    TerminationReason,
    ToolCall,
    ToolResult,
    to_jsonable,
)


@dataclass
class IntelligenceCheckpointData:
    run_state: RunState
    intelligence_store: IntelligenceStore
    artifacts: List[Dict[str, Any]]
    domain_runtime_state: DomainRuntimeState | None = None
    step_checkpoint: "StepCheckpointState | None" = None
    experiment_runtime_state: ExperimentRuntimeState | None = None
    checkpoint_directory: Path | None = None


@dataclass
class StepCheckpointState:
    """Latest durable boundary inside an otherwise incomplete runtime step."""

    run_id: str
    challenge_id: str
    step_id: int
    stage: str
    proposal: ActionProposal
    started_at: datetime
    updated_at: datetime
    tool_results: List[ToolResult] = field(default_factory=list)
    analysis: AnalysisResult | None = None
    approval_events: List[Dict[str, Any]] = field(default_factory=list)
    experiment_update: Dict[str, Any] = field(default_factory=dict)
    experiment_runtime: Dict[str, Any] = field(default_factory=dict)


class IntelligenceCheckpoint:
    """Persist and restore typed runtime, intelligence, and experiment state."""

    RUN_FILE = "run.json"
    INTELLIGENCE_FILE = "intelligence.json"
    ARTIFACTS_FILE = "artifacts.json"
    EXPERIMENTS_FILE = "experiments.json"
    DOMAIN_RUNTIME_FILE = "domain_runtime.json"
    STEP_FILE = "step.json"
    EXPERIMENT_RUNTIME_FILE = "experiment_runtime.json"

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def save(
        self,
        run_state: RunState,
        intelligence_store: IntelligenceStore,
        artifacts: Iterable[Any] = (),
        domain_runtime_state: DomainRuntimeState | None = None,
        experiment_runtime_state: ExperimentRuntimeState | None = None,
    ) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._write_json(self.RUN_FILE, to_jsonable(run_state))
        self._write_json(self.INTELLIGENCE_FILE, intelligence_store.state.to_dict())
        artifact_data = [to_jsonable(artifact) for artifact in artifacts]
        self._write_json(self.ARTIFACTS_FILE, artifact_data)
        self._write_json(
            self.EXPERIMENTS_FILE,
            _experiment_snapshot(intelligence_store.state),
        )
        if domain_runtime_state is not None:
            self._write_json(
                self.DOMAIN_RUNTIME_FILE,
                domain_runtime_state.to_dict(),
            )
        if experiment_runtime_state is not None:
            if experiment_runtime_state.run_id != run_state.run_id:
                raise ValueError("experiment runtime state belongs to a different run")
            if experiment_runtime_state.challenge_id != intelligence_store.state.challenge_id:
                raise ValueError(
                    "experiment runtime state belongs to a different challenge"
                )
            experiment_runtime_state.validate_against(intelligence_store.state)
            self._write_json(
                self.EXPERIMENT_RUNTIME_FILE,
                experiment_runtime_state.to_dict(),
            )
        return self.directory

    def load(self) -> IntelligenceCheckpointData:
        run_raw = self._read_object(self.RUN_FILE)
        intelligence_raw = self._read_object(self.INTELLIGENCE_FILE)
        artifacts_raw = self._read_array(self.ARTIFACTS_FILE)
        domain_state_path = self.directory / self.DOMAIN_RUNTIME_FILE
        domain_runtime_state = (
            _domain_runtime_state_from_dict(self._read_object(self.DOMAIN_RUNTIME_FILE))
            if domain_state_path.is_file()
            else None
        )
        intelligence_state = IntelligenceState.from_dict(intelligence_raw)
        experiment_path = self.directory / self.EXPERIMENTS_FILE
        if experiment_path.is_file():
            experiment_raw = self._read_object(self.EXPERIMENTS_FILE)
            _validate_experiment_snapshot(experiment_raw, intelligence_state)
        _validate_experiment_references(intelligence_state)
        experiment_runtime_path = self.directory / self.EXPERIMENT_RUNTIME_FILE
        experiment_runtime_state = (
            ExperimentRuntimeState.from_dict(
                self._read_object(self.EXPERIMENT_RUNTIME_FILE)
            )
            if experiment_runtime_path.is_file()
            else None
        )
        if experiment_runtime_state is not None:
            if experiment_runtime_state.run_id != str(run_raw.get("run_id", "")):
                raise ValueError("experiment_runtime.json belongs to a different run")
            if experiment_runtime_state.challenge_id != intelligence_state.challenge_id:
                raise ValueError(
                    "experiment_runtime.json belongs to a different challenge"
                )
            experiment_runtime_state.validate_against(intelligence_state)
        step_path = self.directory / self.STEP_FILE
        step_checkpoint = (
            _step_checkpoint_from_dict(self._read_object(self.STEP_FILE))
            if step_path.is_file()
            else None
        )
        if (
            step_checkpoint is not None
            and step_checkpoint.run_id != str(run_raw.get("run_id", ""))
        ):
            raise ValueError("step.json belongs to a different run")
        return IntelligenceCheckpointData(
            run_state=run_state_from_dict(run_raw),
            intelligence_store=IntelligenceStore(intelligence_state),
            artifacts=[dict(item) for item in artifacts_raw if isinstance(item, Mapping)],
            domain_runtime_state=domain_runtime_state,
            step_checkpoint=step_checkpoint,
            experiment_runtime_state=experiment_runtime_state,
            checkpoint_directory=self.directory,
        )

    @classmethod
    def latest(cls, root: str | Path) -> "IntelligenceCheckpoint | None":
        root_path = Path(root)
        if not root_path.exists():
            return None
        candidates = [
            item
            for item in root_path.iterdir()
            if item.is_dir()
            and all((item / name).is_file() for name in (cls.RUN_FILE, cls.INTELLIGENCE_FILE, cls.ARTIFACTS_FILE))
        ]
        if not candidates:
            return None
        return cls(max(candidates, key=lambda item: item.stat().st_mtime))

    def _write_json(self, name: str, payload: Any) -> None:
        path = self.directory / name
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _read_object(self, name: str) -> Dict[str, Any]:
        path = self.directory / name
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{name} must contain a JSON object")
        return raw

    def _read_array(self, name: str) -> List[Any]:
        path = self.directory / name
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"{name} must contain a JSON array")
        return raw


class RuntimeStepCheckpoint:
    """Atomically snapshot RunState and the latest intra-step boundary."""

    STAGES = frozenset(
        {
            "planner_proposal",
            "tool_approval",
            "tool_result",
            "experiment_result",
            "analyzer_result",
            "experiment_update",
            "step_complete",
        }
    )

    def __init__(
        self,
        checkpoint: IntelligenceCheckpoint,
        intelligence_store: IntelligenceStore,
        *,
        artifacts_provider: Callable[[], Iterable[Any]] = lambda: (),
        domain_state_provider: Callable[[], DomainRuntimeState | None] = lambda: None,
        experiment_runtime_provider: Callable[
            [], ExperimentRuntimeState | None
        ] = lambda: None,
    ) -> None:
        self.checkpoint = checkpoint
        self.intelligence_store = intelligence_store
        self.artifacts_provider = artifacts_provider
        self.domain_state_provider = domain_state_provider
        self.experiment_runtime_provider = experiment_runtime_provider

    def record(
        self,
        stage: str,
        state: RunState,
        step_id: int,
        proposal: ActionProposal,
        *,
        started_at: datetime,
        tool_results: Iterable[ToolResult] | None = None,
        analysis: AnalysisResult | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Path:
        if stage not in self.STAGES:
            raise ValueError(f"unsupported step checkpoint stage: {stage}")
        current = self._load_current(state.run_id, step_id)
        approval_events = list(current.approval_events) if current is not None else []
        experiment_update = dict(current.experiment_update) if current is not None else {}
        experiment_runtime = dict(current.experiment_runtime) if current is not None else {}
        if stage == "tool_approval" and metadata is not None:
            approval_events.append(dict(metadata))
        if stage == "experiment_update" and metadata is not None:
            experiment_update = dict(metadata)
        if stage == "experiment_result" and metadata is not None:
            experiment_runtime = dict(metadata)
        current_results = (
            list(tool_results)
            if tool_results is not None
            else list(current.tool_results)
            if current is not None
            else []
        )
        current_analysis = analysis or (current.analysis if current is not None else None)
        snapshot = StepCheckpointState(
            run_id=state.run_id,
            challenge_id=state.challenge.challenge_id,
            step_id=step_id,
            stage=stage,
            proposal=proposal,
            started_at=started_at,
            updated_at=datetime.now(timezone.utc),
            tool_results=current_results,
            analysis=current_analysis,
            approval_events=approval_events,
            experiment_update=experiment_update,
            experiment_runtime=experiment_runtime,
        )
        self.checkpoint.save(
            state,
            self.intelligence_store,
            self.artifacts_provider(),
            self.domain_state_provider(),
            self.experiment_runtime_provider(),
        )
        self.checkpoint._write_json(  # same atomic writer as the parent checkpoint
            IntelligenceCheckpoint.STEP_FILE,
            _step_checkpoint_to_dict(snapshot),
        )
        return self.checkpoint.directory

    def finalize(self, state: RunState) -> Path:
        """Persist terminal Runtime and domain state after final review hooks."""

        return self.checkpoint.save(
            state,
            self.intelligence_store,
            self.artifacts_provider(),
            self.domain_state_provider(),
            self.experiment_runtime_provider(),
        )

    def _load_current(
        self,
        run_id: str,
        step_id: int,
    ) -> StepCheckpointState | None:
        path = self.checkpoint.directory / IntelligenceCheckpoint.STEP_FILE
        if not path.is_file():
            return None
        raw = self.checkpoint._read_object(IntelligenceCheckpoint.STEP_FILE)
        current = _step_checkpoint_from_dict(raw)
        if current.run_id != run_id or current.step_id != step_id:
            return None
        return current


def _experiment_snapshot(state: IntelligenceState) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "challenge_id": state.challenge_id,
        "hypotheses": to_jsonable(state.hypotheses),
        "experiments": to_jsonable(state.experiments),
        "evidence": to_jsonable(state.evidence),
    }


def _validate_experiment_snapshot(
    data: Mapping[str, Any],
    state: IntelligenceState,
) -> None:
    if data.get("schema_version") != 1:
        raise ValueError("unsupported experiments.json schema version")
    if str(data.get("challenge_id", "")) != state.challenge_id:
        raise ValueError("experiments.json belongs to a different challenge")
    expected = _experiment_snapshot(state)
    for name in ("hypotheses", "experiments", "evidence"):
        if data.get(name) != expected[name]:
            raise ValueError(f"experiments.json is inconsistent with intelligence.json: {name}")


def _validate_experiment_references(state: IntelligenceState) -> None:
    hypothesis_ids = {item.id for item in state.hypotheses}
    experiment_by_id = {item.experiment_id: item for item in state.experiments}
    evidence_by_id = {item.evidence_id: item for item in state.evidence}
    if len(experiment_by_id) != len(state.experiments):
        raise ValueError("duplicate experiment id in checkpoint")
    if len(evidence_by_id) != len(state.evidence):
        raise ValueError("duplicate evidence id in checkpoint")
    for experiment in state.experiments:
        if experiment.hypothesis_id not in hypothesis_ids:
            raise ValueError("experiment references an unknown hypothesis")
    for evidence in state.evidence:
        experiment = experiment_by_id.get(evidence.experiment_id)
        if experiment is None:
            raise ValueError("evidence references an unknown experiment")
        if evidence.hypothesis_id != experiment.hypothesis_id:
            raise ValueError("evidence hypothesis does not match its experiment")
    for hypothesis in state.hypotheses:
        if (
            hypothesis.status.value in {"CONFIRMED", "REJECTED"}
            and not hypothesis.evidence_refs
        ):
            # Pre-R6 checkpoints used enum confidence and could close a
            # hypothesis without an experiment record. Keep those snapshots
            # loadable while enforcing evidence for R6 numeric-confidence state.
            if isinstance(hypothesis.confidence, (int, float)):
                raise ValueError("closed hypothesis has no evidence")
            continue
        for evidence_id in hypothesis.evidence_refs:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None or evidence.hypothesis_id != hypothesis.id:
                raise ValueError("hypothesis references inconsistent evidence")
            experiment = experiment_by_id[evidence.experiment_id]
            if experiment.status.value not in {"SUCCESS", "FAILED"}:
                raise ValueError("closed hypothesis references an unfinished experiment")


def _domain_runtime_state_from_dict(
    data: Mapping[str, Any],
) -> DomainRuntimeState:
    if str(data.get("domain", "")) == "web":
        from agent.domains.web.state import WebRuntimeState

        return WebRuntimeState.from_dict(data)
    return DomainRuntimeState.from_dict(data)


def _step_checkpoint_to_dict(state: StepCheckpointState) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": state.run_id,
        "challenge_id": state.challenge_id,
        "step_id": state.step_id,
        "stage": state.stage,
        "proposal": to_jsonable(state.proposal),
        "started_at": state.started_at.isoformat(),
        "updated_at": state.updated_at.isoformat(),
        "tool_results": to_jsonable(state.tool_results),
        "analysis": to_jsonable(state.analysis) if state.analysis is not None else None,
        "approval_events": to_jsonable(state.approval_events),
        "experiment_update": to_jsonable(state.experiment_update),
        "experiment_runtime": to_jsonable(state.experiment_runtime),
    }


def _step_checkpoint_from_dict(data: Mapping[str, Any]) -> StepCheckpointState:
    if data.get("schema_version") != 1:
        raise ValueError("unsupported step.json schema version")
    stage = str(data.get("stage", ""))
    if stage not in RuntimeStepCheckpoint.STAGES:
        raise ValueError("step.json contains an unknown stage")
    analysis_raw = data.get("analysis")
    return StepCheckpointState(
        run_id=str(data["run_id"]),
        challenge_id=str(data["challenge_id"]),
        step_id=int(data["step_id"]),
        stage=stage,
        proposal=_proposal_from_dict(_object(data, "proposal")),
        started_at=_datetime(data.get("started_at")),
        updated_at=_datetime(data.get("updated_at")),
        tool_results=[
            _tool_result_from_dict(_mapping(item))
            for item in _array(data.get("tool_results"))
        ],
        analysis=(
            _analysis_from_dict(_mapping(analysis_raw))
            if isinstance(analysis_raw, Mapping)
            else None
        ),
        approval_events=[
            dict(item)
            for item in _array(data.get("approval_events"))
            if isinstance(item, Mapping)
        ],
        experiment_update=dict(data.get("experiment_update", {})),
        experiment_runtime=dict(data.get("experiment_runtime", {})),
    )

def run_state_from_dict(data: Mapping[str, Any]) -> RunState:
    """Rehydrate only typed R0 contracts, never historical chat memory."""

    challenge_raw = _object(data, "challenge")
    state = RunState(
        challenge=ChallengeSpec(
            challenge_id=str(challenge_raw["challenge_id"]),
            title=str(challenge_raw["title"]),
            description=str(challenge_raw["description"]),
            category=_optional_string(challenge_raw.get("category")),
            authorization_scope=str(challenge_raw.get("authorization_scope", "authorized_ctf_only")),
            metadata=dict(challenge_raw.get("metadata", {})),
        ),
        run_id=str(data["run_id"]),
        parent_run_id=_optional_string(data.get("parent_run_id")),
    )
    for raw_step in _array(data.get("steps")):
        state.record_step(_step_from_dict(_mapping(raw_step)))
    state.status = RunStatus(str(data.get("status", RunStatus.CREATED.value)))
    state.current_step = int(data.get("current_step", state.current_step))
    counters_raw = data.get("counters", {})
    state.counters = RunCounters(**dict(counters_raw) if isinstance(counters_raw, Mapping) else {})
    raw_last = data.get("last_analysis")
    state.last_analysis = _analysis_from_dict(_mapping(raw_last)) if isinstance(raw_last, Mapping) else None
    raw_termination = data.get("termination")
    state.termination = _termination_from_dict(_mapping(raw_termination)) if isinstance(raw_termination, Mapping) else None
    action_counts = data.get("action_counts", {})
    state.action_counts = {str(key): int(value) for key, value in action_counts.items()} if isinstance(action_counts, Mapping) else {}
    response_counts = data.get("response_counts", {})
    state.response_counts = {str(key): int(value) for key, value in response_counts.items()} if isinstance(response_counts, Mapping) else {}
    return state


def _step_from_dict(data: Mapping[str, Any]) -> StepRecord:
    proposal = _proposal_from_dict(_object(data, "proposal"))
    tool_results = [_tool_result_from_dict(_mapping(item)) for item in _array(data.get("tool_results"))]
    observation_raw = _object(data, "observation")
    observation = Observation(
        step_id=int(observation_raw["step_id"]),
        objective=str(observation_raw["objective"]),
        proposal=_proposal_from_dict(_object(observation_raw, "proposal")),
        tool_results=[
            _tool_result_from_dict(_mapping(item)) for item in _array(observation_raw.get("tool_results"))
        ],
        state_view=dict(observation_raw.get("state_view", {})),
        observation_id=str(
            observation_raw.get("observation_id")
            or f"observation-restored-{data.get('step_id', 'unknown')}"
        ),
    )
    return StepRecord(
        step_id=int(data["step_id"]),
        proposal=proposal,
        tool_results=tool_results,
        observation=observation,
        analysis=_analysis_from_dict(_object(data, "analysis")),
        started_at=_datetime(data["started_at"]),
        finished_at=_datetime(data["finished_at"]),
    )


def _proposal_from_dict(data: Mapping[str, Any]) -> ActionProposal:
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
            for item in _array(data.get("actions"))
            if isinstance(item, Mapping)
        ],
        metadata=dict(data.get("metadata", {})),
        decision_type=str(data.get("decision_type", "normal_action")),
    )


def _tool_result_from_dict(data: Mapping[str, Any]) -> ToolResult:
    return ToolResult(
        call_id=str(data["call_id"]),
        tool_name=str(data["tool_name"]),
        success=bool(data["success"]),
        exit_code=data.get("exit_code"),
        stdout=str(data.get("stdout", "")),
        stderr=str(data.get("stderr", "")),
        error=_optional_string(data.get("error")),
        started_at=_datetime(data.get("started_at")),
        finished_at=_datetime(data.get("finished_at")),
        duration=float(data.get("duration", 0.0)),
        metadata=dict(data.get("metadata", {})),
        artifact_refs=[str(item) for item in _array(data.get("artifact_refs"))],
        execution_context=dict(data.get("execution_context", {})),
        policy_decision=dict(data["policy_decision"]) if isinstance(data.get("policy_decision"), Mapping) else None,
        tool_error=(
            {str(key): str(value) for key, value in data["tool_error"].items()}
            if isinstance(data.get("tool_error"), Mapping)
            else None
        ),
    )


def _analysis_from_dict(data: Mapping[str, Any]) -> AnalysisResult:
    candidates = [
        FlagCandidate(
            value=str(item["value"]),
            source=str(item["source"]),
            confidence=float(item["confidence"]),
            evidence=str(item["evidence"]),
            kind=FlagCandidateKind(str(item.get("kind", "FLAG")).upper()),
        )
        for item in _array(data.get("flag_candidates"))
        if isinstance(item, Mapping)
    ]
    suggestions = [
        KnowledgeUpdateSuggestion.from_dict(item)
        for item in _array(data.get("knowledge_updates"))
        if isinstance(item, Mapping)
    ]
    return AnalysisResult(
        summary=str(data["summary"]),
        outcome=AnalysisOutcome(str(data["outcome"])),
        recommendations=str(data.get("recommendations", "")),
        flag_candidates=candidates,
        confidence=float(data.get("confidence", 0.0)),
        knowledge_updates=suggestions,
    )


def _termination_from_dict(data: Mapping[str, Any]) -> TerminationDecision:
    candidate = data.get("flag_candidate")
    return TerminationDecision(
        status=RunStatus(str(data["status"])),
        reason=TerminationReason(str(data["reason"])),
        message=str(data.get("message", "")),
        flag_candidate=(
            FlagCandidate(
                value=str(candidate["value"]),
                source=str(candidate["source"]),
                confidence=float(candidate["confidence"]),
                evidence=str(candidate["evidence"]),
                kind=FlagCandidateKind(str(candidate.get("kind", "FLAG")).upper()),
            )
            if isinstance(candidate, Mapping)
            else None
        ),
    )


def _array(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("checkpoint entry must be an object")
    return value


def _object(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    return _mapping(data.get(name))


def _datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("checkpoint timestamp must be an ISO string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None
