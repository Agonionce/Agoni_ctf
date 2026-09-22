"""Typed contracts shared by the Agonionce R0 runtime components."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from agent.intelligence.models import KnowledgeUpdateSuggestion
from agent.runtime.errors import ContractValidationError


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field_name} must be a non-empty string")


class RunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SOLVED = "SOLVED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    ABORTED = "ABORTED"
    PAUSED = "PAUSED"


class AnalysisOutcome(str, Enum):
    PROGRESS = "PROGRESS"
    NO_PROGRESS = "NO_PROGRESS"
    ACTION_FAILED = "ACTION_FAILED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NEEDS_REPLAN = "NEEDS_REPLAN"


class DecisionType(str, Enum):
    """Backward-compatible routing hint for one ActionProposal."""

    NORMAL_ACTION = "normal_action"
    EXPERIMENT_ACTION = "experiment_action"


class TerminationReason(str, Enum):
    NONE = "NONE"
    FLAG_CONFIRMED = "FLAG_CONFIRMED"
    MAX_STEPS = "MAX_STEPS"
    MAX_RUNTIME = "MAX_RUNTIME"
    MAX_LLM_CALLS = "MAX_LLM_CALLS"
    PLANNER_RETRY_EXHAUSTED = "PLANNER_RETRY_EXHAUSTED"
    PARSER_RETRY_EXHAUSTED = "PARSER_RETRY_EXHAUSTED"
    CONSECUTIVE_FAILURES = "CONSECUTIVE_FAILURES"
    DUPLICATE_ACTIONS = "DUPLICATE_ACTIONS"
    EXPLICIT_ABORT = "EXPLICIT_ABORT"
    NO_ACTIONS = "NO_ACTIONS"
    FATAL_ERROR = "FATAL_ERROR"


class FlagCandidateKind(str, Enum):
    """The semantic role of a value noticed during analysis.

    A password or a promising lead may be useful evidence, but neither is a
    challenge answer.  Keeping that distinction in the runtime contract
    prevents an automatic run from treating arbitrary extracted text as a
    solved Flag.
    """

    FLAG = "FLAG"
    PASSWORD = "PASSWORD"
    LEAD = "LEAD"


@dataclass
class ChallengeSpec:
    """The R0 challenge identity and authorized scope declaration."""

    challenge_id: str
    title: str
    description: str
    category: Optional[str] = None
    authorization_scope: str = "authorized_ctf_only"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.challenge_id, "challenge_id")
        _require_text(self.title, "title")
        _require_text(self.description, "description")
        _require_text(self.authorization_scope, "authorization_scope")
        if not isinstance(self.metadata, dict):
            raise ContractValidationError("metadata must be a dictionary")


@dataclass
class RunBudget:
    """Hard limits that bound one AgentRuntime execution."""

    max_steps: int = 100
    max_runtime: float = 7200
    max_planner_retries: int = 8
    max_parser_retries: int = 6
    max_consecutive_failures: int = 12
    max_duplicate_actions: int = 6
    max_llm_calls: int = 250

    def validate(self) -> "RunBudget":
        integer_fields = (
            "max_steps",
            "max_planner_retries",
            "max_parser_retries",
            "max_consecutive_failures",
            "max_duplicate_actions",
            "max_llm_calls",
        )
        for field_name in integer_fields:
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ContractValidationError(f"{field_name} must be an integer > 0")
        if (
            not isinstance(self.max_runtime, (int, float))
            or isinstance(self.max_runtime, bool)
            or self.max_runtime <= 0
        ):
            raise ContractValidationError("max_runtime must be a number > 0")
        return self

    @classmethod
    def from_mapping(cls, data: Optional[Dict[str, Any]]) -> "RunBudget":
        """Build a budget from optional config, preserving R0 defaults."""

        if data is None:
            return cls().validate()
        if not isinstance(data, dict):
            raise ContractValidationError("runtime configuration must be a dictionary")
        allowed = {
            "max_steps",
            "max_runtime",
            "max_planner_retries",
            "max_parser_retries",
            "max_consecutive_failures",
            "max_duplicate_actions",
            "max_llm_calls",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ContractValidationError(
                f"unknown runtime budget fields: {', '.join(unknown)}"
            )
        return cls(**data).validate()


@dataclass
class RunCounters:
    """Counters used for budget and observability decisions."""

    step_count: int = 0
    llm_calls: int = 0
    planner_calls: int = 0
    analyzer_calls: int = 0
    parser_retries: int = 0
    consecutive_failures: int = 0
    failure_count: int = 0
    duplicate_actions: int = 0
    repeated_responses: int = 0


@dataclass
class ToolCall:
    """One typed request to a named tool."""

    call_id: str
    tool_name: str
    arguments: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.call_id, "call_id")
        _require_text(self.tool_name, "tool_name")
        if not isinstance(self.arguments, dict):
            raise ContractValidationError("ToolCall.arguments must be a dictionary")
        if not isinstance(self.metadata, dict):
            raise ContractValidationError("ToolCall.metadata must be a dictionary")

    def fingerprint(self) -> str:
        """Return a stable identity for duplicate-action detection."""

        normalized = json.dumps(
            {"tool_name": self.tool_name, "arguments": self.arguments},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        return normalized


@dataclass
class ActionProposal:
    """Planner output consumed by the Executor."""

    objective: str
    reasoning_summary: str
    actions: List[ToolCall]
    metadata: Dict[str, Any] = field(default_factory=dict)
    decision_type: DecisionType = DecisionType.NORMAL_ACTION

    def __post_init__(self) -> None:
        _require_text(self.objective, "objective")
        _require_text(self.reasoning_summary, "reasoning_summary")
        if not isinstance(self.actions, list) or not self.actions:
            raise ContractValidationError("ActionProposal.actions must not be empty")
        if not all(isinstance(action, ToolCall) for action in self.actions):
            raise ContractValidationError("actions must contain ToolCall objects")
        if not isinstance(self.metadata, dict):
            raise ContractValidationError("ActionProposal.metadata must be a dictionary")
        if isinstance(self.decision_type, str):
            aliases = {
                "normal": DecisionType.NORMAL_ACTION,
                "normal_action": DecisionType.NORMAL_ACTION,
                "experiment": DecisionType.EXPERIMENT_ACTION,
                "experiment_action": DecisionType.EXPERIMENT_ACTION,
            }
            normalized = aliases.get(self.decision_type.lower())
            if normalized is None:
                raise ContractValidationError("ActionProposal.decision_type is invalid")
            self.decision_type = normalized
        if not isinstance(self.decision_type, DecisionType):
            raise ContractValidationError("ActionProposal.decision_type is invalid")
        if self.decision_type is DecisionType.EXPERIMENT_ACTION:
            if len(self.actions) != 1:
                raise ContractValidationError(
                    "experiment_action requires exactly one ToolCall"
                )
            experiment = self.metadata.get("experiment")
            if not isinstance(experiment, dict):
                raise ContractValidationError(
                    "experiment_action requires experiment metadata"
                )
            hypothesis_id = experiment.get("hypothesis_id")
            statement = experiment.get("hypothesis_statement")
            if not any(
                isinstance(value, str) and value.strip()
                for value in (hypothesis_id, statement)
            ):
                raise ContractValidationError(
                    "experiment_action requires hypothesis_id or hypothesis_statement"
                )
            for name in ("goal", "expected_result"):
                value = experiment.get(name)
                if not isinstance(value, str) or not value.strip():
                    raise ContractValidationError(
                        f"experiment_action requires {name}"
                    )


@dataclass
class ToolResult:
    """Normalized result returned by an Executor."""

    call_id: str
    tool_name: str
    success: bool
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime = field(default_factory=utc_now)
    duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifact_refs: List[str] = field(default_factory=list)
    execution_context: Dict[str, Any] = field(default_factory=dict)
    policy_decision: Optional[Dict[str, str]] = None
    tool_error: Optional[Dict[str, str]] = None

    def __post_init__(self) -> None:
        _require_text(self.call_id, "call_id")
        _require_text(self.tool_name, "tool_name")
        if not isinstance(self.success, bool):
            raise ContractValidationError("ToolResult.success must be boolean")
        if not isinstance(self.stdout, str) or not isinstance(self.stderr, str):
            raise ContractValidationError("ToolResult stdout/stderr must be strings")
        if self.duration < 0:
            raise ContractValidationError("ToolResult.duration must be >= 0")
        if not isinstance(self.metadata, dict):
            raise ContractValidationError("ToolResult.metadata must be a dictionary")
        if not isinstance(self.artifact_refs, list) or not all(
            isinstance(reference, str) for reference in self.artifact_refs
        ):
            raise ContractValidationError("ToolResult.artifact_refs must be a list of strings")
        if not isinstance(self.execution_context, dict):
            raise ContractValidationError(
                "ToolResult.execution_context must be a dictionary"
            )
        if self.policy_decision is not None and not isinstance(
            self.policy_decision, dict
        ):
            raise ContractValidationError(
                "ToolResult.policy_decision must be a dictionary or None"
            )
        if self.tool_error is not None and not isinstance(self.tool_error, dict):
            raise ContractValidationError(
                "ToolResult.tool_error must be a dictionary or None"
            )


@dataclass
class Observation:
    """Structured evidence passed from Executor to Analyzer."""

    step_id: int
    objective: str
    proposal: ActionProposal
    tool_results: List[ToolResult]
    state_view: Dict[str, Any] = field(default_factory=dict)
    observation_id: str = field(
        default_factory=lambda: f"observation-{uuid.uuid4().hex[:12]}"
    )

    def __post_init__(self) -> None:
        if not isinstance(self.step_id, int) or self.step_id <= 0:
            raise ContractValidationError("Observation.step_id must be an integer > 0")
        _require_text(self.objective, "objective")
        if not isinstance(self.proposal, ActionProposal):
            raise ContractValidationError("Observation.proposal must be ActionProposal")
        if not isinstance(self.tool_results, list):
            raise ContractValidationError("Observation.tool_results must be a list")
        _require_text(self.observation_id, "Observation.observation_id")


@dataclass
class FlagCandidate:
    """A typed value noticed during analysis that may require confirmation."""

    value: str
    source: str
    confidence: float
    evidence: str
    kind: FlagCandidateKind = FlagCandidateKind.FLAG

    def __post_init__(self) -> None:
        _require_text(self.value, "FlagCandidate.value")
        _require_text(self.source, "FlagCandidate.source")
        _require_text(self.evidence, "FlagCandidate.evidence")
        if not isinstance(self.kind, FlagCandidateKind):
            raise ContractValidationError("FlagCandidate.kind must be FlagCandidateKind")
        if not 0 <= self.confidence <= 1:
            raise ContractValidationError("FlagCandidate.confidence must be in [0, 1]")

    def rejection_reason(self) -> str | None:
        """Return why this cannot be used as a final Flag without inspection.

        This deliberately avoids a format-specific Flag regex: local CTFs may
        use arbitrary token formats.  It rejects only values that are plainly
        prose, control text, or a non-Flag semantic role.
        """

        if self.kind is not FlagCandidateKind.FLAG:
            return f"candidate kind is {self.kind.value}, not FLAG"
        if len(self.value) > 512:
            return "candidate is too long to be a single Flag value"
        if any(character.isspace() or ord(character) < 32 for character in self.value):
            return "candidate is descriptive text rather than one Flag value"
        return None


@dataclass
class AnalysisResult:
    """Typed interpretation of one Observation."""

    summary: str
    outcome: AnalysisOutcome
    recommendations: str = ""
    flag_candidates: List[FlagCandidate] = field(default_factory=list)
    confidence: float = 0.0
    knowledge_updates: List[KnowledgeUpdateSuggestion] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_text(self.summary, "AnalysisResult.summary")
        if not isinstance(self.outcome, AnalysisOutcome):
            raise ContractValidationError("AnalysisResult.outcome must be AnalysisOutcome")
        if not isinstance(self.recommendations, str):
            raise ContractValidationError("recommendations must be a string")
        if not all(isinstance(item, FlagCandidate) for item in self.flag_candidates):
            raise ContractValidationError("flag_candidates must contain FlagCandidate objects")
        if not all(
            isinstance(item, KnowledgeUpdateSuggestion)
            for item in self.knowledge_updates
        ):
            raise ContractValidationError(
                "knowledge_updates must contain KnowledgeUpdateSuggestion objects"
            )
        if not 0 <= self.confidence <= 1:
            raise ContractValidationError("AnalysisResult.confidence must be in [0, 1]")


@dataclass
class StepRecord:
    """Complete record of one Planner → Executor → Analyzer cycle."""

    step_id: int
    proposal: ActionProposal
    tool_results: List[ToolResult]
    observation: Observation
    analysis: AnalysisResult
    started_at: datetime
    finished_at: datetime


@dataclass
class TerminationDecision:
    """A single terminal or continuing decision from the controller."""

    status: RunStatus
    reason: TerminationReason
    message: str = ""
    flag_candidate: Optional[FlagCandidate] = None


@dataclass
class RunState:
    """Authoritative R0 state; legacy Memory is not part of this contract."""

    challenge: ChallengeSpec
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_run_id: Optional[str] = None
    status: RunStatus = RunStatus.CREATED
    current_step: int = 0
    steps: List[StepRecord] = field(default_factory=list)
    counters: RunCounters = field(default_factory=RunCounters)
    last_analysis: Optional[AnalysisResult] = None
    termination: Optional[TerminationDecision] = None
    action_counts: Dict[str, int] = field(default_factory=dict)
    response_counts: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.challenge, ChallengeSpec):
            raise ContractValidationError("RunState.challenge must be ChallengeSpec")
        _require_text(self.run_id, "run_id")
        if self.parent_run_id is not None:
            _require_text(self.parent_run_id, "RunState.parent_run_id")

    def record_step(self, record: StepRecord) -> None:
        if record.step_id != self.current_step + 1:
            raise ContractValidationError("StepRecord ids must be sequential")
        self.steps.append(record)
        self.current_step = record.step_id
        self.counters.step_count = self.current_step
        self.last_analysis = record.analysis

    def set_termination(self, decision: TerminationDecision) -> None:
        self.termination = decision
        self.status = decision.status

    def fork_for_resume(self) -> str:
        """Create a distinct run identity while retaining recoverable state.

        The old checkpoint remains immutable.  The new run records its direct
        parent so an operator can reconcile a resumed attempt with the attempt
        that supplied its starting evidence.
        """

        parent_run_id = self.run_id
        self.run_id = str(uuid.uuid4())
        self.parent_run_id = parent_run_id
        self.status = RunStatus.CREATED
        self.termination = None
        return parent_run_id

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self)  # type: ignore[return-value]


def to_jsonable(value: Any) -> Any:
    """Convert contracts into JSON-compatible values for diagnostics/checkpoints."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
