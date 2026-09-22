"""Bounded orchestration for the Agonionce R0 core runtime."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from agent.intelligence.store import IntelligenceStore
from agent.intelligence.updater import KnowledgeUpdater
from agent.runtime.analyzer import Analyzer
from agent.runtime.budget import BudgetTracker
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    DecisionType,
    Observation,
    RunBudget,
    RunState,
    RunStatus,
    StepRecord,
    TerminationDecision,
    TerminationReason,
    ToolResult,
)
from agent.runtime.errors import BudgetExceeded, PlannerOutputError
from agent.runtime.executor import Executor
from agent.runtime.planner import Planner
from agent.runtime.termination import TerminationController

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Coordinate Planner, Executor, Analyzer and TerminationController."""

    def __init__(
        self,
        challenge: ChallengeSpec,
        planner: Planner,
        executor: Executor,
        analyzer: Analyzer,
        budget: Optional[RunBudget] = None,
        termination: Optional[TerminationController] = None,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        flag_confirmer: Optional[Callable[[object], bool]] = None,
        intelligence_store: Optional[IntelligenceStore] = None,
        knowledge_updater: Optional[KnowledgeUpdater] = None,
        initial_state: Optional[RunState] = None,
        checkpoint_handler: Any = None,
        initial_step_checkpoint: Any = None,
        experiment_orchestrator: Any = None,
    ) -> None:
        self.challenge = challenge
        self.planner = planner
        self.executor = executor
        self.analyzer = analyzer
        self.budget = (budget or RunBudget()).validate()
        if initial_state is not None and initial_state.challenge.challenge_id != challenge.challenge_id:
            raise ValueError("initial RunState belongs to a different challenge")
        self.state = initial_state or RunState(challenge=challenge)
        self.tracker = BudgetTracker(self.budget, self.state.counters)
        self.termination = termination or TerminationController(self.budget)
        self.tool_schemas = tool_schemas or []
        self.flag_confirmer = flag_confirmer
        self.intelligence_store = intelligence_store
        self.knowledge_updater = knowledge_updater or (
            KnowledgeUpdater(intelligence_store) if intelligence_store is not None else None
        )
        self.checkpoint_handler = checkpoint_handler
        self.initial_step_checkpoint = initial_step_checkpoint
        self.experiment_orchestrator = experiment_orchestrator
        self._abort_requested = False
        self._active_step_id = 0
        self._active_proposal: ActionProposal | None = None
        self._active_started_at: datetime | None = None
        self._active_tool_results: List[ToolResult] = []

    def request_abort(self) -> None:
        """Request a safe stop at the next runtime boundary."""

        self._abort_requested = True

    def run(self) -> RunState:
        self.tracker.start()
        self.state.status = RunStatus.RUNNING
        pending_step = self._resumable_step_checkpoint()

        while self.state.status == RunStatus.RUNNING:
            if self._abort_requested:
                return self._finish(
                    TerminationDecision(
                        RunStatus.ABORTED,
                        TerminationReason.EXPLICIT_ABORT,
                        "runtime abort requested",
                    )
                )

            pre_step = self.tracker.pre_step_decision(self.state)
            if pre_step is not None:
                return self._finish(pre_step)

            resume_stage = ""
            if pending_step is not None:
                proposal = pending_step.proposal
                step_id = pending_step.step_id
                started_at = pending_step.started_at
                resume_stage = pending_step.stage
                pending_step = None
            else:
                resumed_experiment = self._pending_experiment_proposal()
                if resumed_experiment is not None:
                    proposal, started_at = resumed_experiment
                    step_id = self.state.current_step + 1
                    resume_stage = "planner_proposal"
                else:
                    proposal, plan_decision = self._plan_with_bounds()
                    if plan_decision is not None:
                        return self._finish(plan_decision)
                    assert proposal is not None
                    duplicate_decision = self.tracker.register_actions(self.state, proposal)
                    if duplicate_decision is not None:
                        return self._finish(duplicate_decision)
                    step_id = self.state.current_step + 1
                    started_at = datetime.now(timezone.utc)

            self._active_step_id = step_id
            self._active_proposal = proposal
            self._active_started_at = started_at
            checkpoint_matches_step = (
                resume_stage
                and self.initial_step_checkpoint is not None
                and getattr(self.initial_step_checkpoint, "step_id", 0) == step_id
            )
            self._active_tool_results = list(
                getattr(self.initial_step_checkpoint, "tool_results", [])
                if checkpoint_matches_step
                else []
            )
            try:
                experiment_record = self._prepare_experiment(proposal, step_id)
                if not resume_stage:
                    self._checkpoint("planner_proposal")
                if experiment_record is not None and not self._active_tool_results:
                    restored_results = self.experiment_orchestrator.restored_tool_results(
                        step_id
                    )
                    if restored_results:
                        self._active_tool_results = restored_results
                        resume_stage = "experiment_result"
                # R1 executors may need the Runtime-owned state to create an
                # isolated execution context. Older Executor implementations
                # remain compatible because this hook is optional.
                if resume_stage in {
                    "tool_result",
                    "experiment_result",
                    "analyzer_result",
                    "experiment_update",
                }:
                    tool_results = list(self._active_tool_results)
                else:
                    prepare = getattr(self.executor, "prepare", None)
                    if callable(prepare):
                        prepare(self.state, step_id, proposal)
                    tool_results = self.executor.execute(proposal)
                    self._active_tool_results = list(tool_results)
                    self._checkpoint("tool_result", tool_results=tool_results)
                observation = Observation(
                    step_id=step_id,
                    objective=proposal.objective,
                    proposal=proposal,
                    tool_results=tool_results,
                    state_view={
                        "current_step": self.state.current_step,
                        "status": self.state.status.value,
                        "decision_type": proposal.decision_type.value,
                    },
                    observation_id=self._observation_id(step_id, experiment_record),
                )
                repeated_response_calls = self.tracker.register_response_fingerprints(
                    self.state,
                    tool_results,
                )
                if repeated_response_calls:
                    observation.state_view["repeated_response_calls"] = repeated_response_calls
                if experiment_record is not None and resume_stage not in {
                    "experiment_result",
                    "analyzer_result",
                    "experiment_update",
                }:
                    evaluation = self.experiment_orchestrator.complete(
                        proposal,
                        observation,
                    )
                    self._checkpoint(
                        "experiment_result",
                        tool_results=tool_results,
                        metadata=(
                            evaluation.to_dict()
                            if evaluation is not None
                            else {}
                        ),
                    )
                if resume_stage in {"analyzer_result", "experiment_update"}:
                    analysis = getattr(self.initial_step_checkpoint, "analysis", None)
                    if analysis is None:
                        raise ValueError("step checkpoint is missing analyzer result")
                else:
                    analysis, analyzer_decision = self._analyze_with_bounds(
                        observation,
                    )
                    if analyzer_decision is not None:
                        return self._finish(analyzer_decision)
                    assert analysis is not None
                    if repeated_response_calls:
                        analysis = self._mark_repeated_response(analysis)
                    self._checkpoint(
                        "analyzer_result",
                        tool_results=tool_results,
                        analysis=analysis,
                    )
                if resume_stage != "experiment_update":
                    if self.knowledge_updater is not None:
                        self.knowledge_updater.apply(analysis, observation)
                    if self.experiment_orchestrator is not None:
                        self.experiment_orchestrator.advance_loop(
                            observation,
                            analysis,
                        )
                    self._checkpoint(
                        "experiment_update",
                        tool_results=tool_results,
                        analysis=analysis,
                        metadata=self._experiment_checkpoint_metadata(),
                    )
            except BudgetExceeded:
                return self._finish(
                    TerminationDecision(
                        RunStatus.BUDGET_EXHAUSTED,
                        TerminationReason.MAX_LLM_CALLS,
                        "max_llm_calls reached before analyzer",
                    )
                )
            except Exception as error:
                logger.exception("R0 runtime step failed")
                return self._finish(
                    TerminationDecision(
                        RunStatus.FAILED,
                        TerminationReason.FATAL_ERROR,
                        str(error),
                    )
                )

            finished_at = datetime.now(timezone.utc)
            record = StepRecord(
                step_id=step_id,
                proposal=proposal,
                tool_results=tool_results,
                observation=observation,
                analysis=analysis,
                started_at=started_at,
                finished_at=finished_at,
            )
            self.state.record_step(record)
            self.tracker.record_outcome(analysis.outcome)
            self._checkpoint(
                "step_complete",
                tool_results=tool_results,
                analysis=analysis,
            )

            decision = self.termination.evaluate(
                self.state,
                budget_decision=self.tracker.pre_step_decision(self.state),
                flag_confirmer=self.flag_confirmer,
            )
            if decision.status != RunStatus.RUNNING:
                return self._finish(decision)

        return self.state

    def record_tool_event(self, stage: str, metadata: Dict[str, Any]) -> None:
        """Persist ToolRuntime approval boundaries without owning approval logic."""

        if stage != "tool_approval" or self._active_proposal is None:
            return
        self._checkpoint(stage, metadata=metadata)

    def _checkpoint(
        self,
        stage: str,
        *,
        tool_results: List[ToolResult] | None = None,
        analysis: AnalysisResult | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        if self.checkpoint_handler is None or self._active_proposal is None:
            return
        if self._active_started_at is None or self._active_step_id <= 0:
            raise RuntimeError("step checkpoint requested without an active step")
        self.checkpoint_handler.record(
            stage,
            self.state,
            self._active_step_id,
            self._active_proposal,
            started_at=self._active_started_at,
            tool_results=tool_results,
            analysis=analysis,
            metadata=metadata,
        )

    def _resumable_step_checkpoint(self) -> Any:
        pending = self.initial_step_checkpoint
        if pending is None or getattr(pending, "stage", "") == "step_complete":
            return None
        if pending.run_id != self.state.run_id:
            raise ValueError("step checkpoint belongs to a different run")
        if pending.challenge_id != self.challenge.challenge_id:
            raise ValueError("step checkpoint belongs to a different challenge")
        if pending.step_id != self.state.current_step + 1:
            raise ValueError("step checkpoint is not the next sequential step")
        return pending

    def _experiment_checkpoint_metadata(self) -> Dict[str, Any]:
        if self.intelligence_store is None:
            return {
                "hypotheses": 0,
                "experiments": 0,
                "evidence": 0,
                "runtime_experiments": 0,
            }
        state = self.intelligence_store.state
        runtime_experiments = (
            len(self.experiment_orchestrator.state.records)
            if self.experiment_orchestrator is not None
            else 0
        )
        return {
            "hypotheses": len(state.hypotheses),
            "experiments": len(state.experiments),
            "evidence": len(state.evidence),
            "runtime_experiments": runtime_experiments,
            "experiment_loop_iteration": (
                self.experiment_orchestrator.state.loop_iteration
                if self.experiment_orchestrator is not None
                else 0
            ),
            "experiment_decisions": (
                len(self.experiment_orchestrator.state.decision_history)
                if self.experiment_orchestrator is not None
                else 0
            ),
        }

    def _prepare_experiment(
        self,
        proposal: ActionProposal,
        step_id: int,
    ) -> Any:
        if self.experiment_orchestrator is None:
            if proposal.decision_type is DecisionType.EXPERIMENT_ACTION:
                raise RuntimeError(
                    "experiment_action requires an ExperimentOrchestrator"
                )
            return None
        return self.experiment_orchestrator.prepare(
            proposal,
            step_id=step_id,
            run_id=self.state.run_id,
            challenge_id=self.challenge.challenge_id,
        )

    def _pending_experiment_proposal(
        self,
    ) -> tuple[ActionProposal, datetime] | None:
        if self.experiment_orchestrator is None:
            return None
        step_id = self.state.current_step + 1
        proposal = self.experiment_orchestrator.pending_proposal(step_id)
        if proposal is None:
            return None
        record = self.experiment_orchestrator.record_for_step(step_id)
        if record is None:
            raise ValueError("pending experiment proposal has no runtime record")
        try:
            started_at = datetime.fromisoformat(record.created_at)
        except ValueError:
            started_at = datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        return proposal, started_at

    def _observation_id(self, step_id: int, experiment_record: Any) -> str:
        if experiment_record is not None and experiment_record.observation_id:
            return str(experiment_record.observation_id)
        return f"observation-{self.state.run_id}-{step_id:04d}"

    def _plan_with_bounds(
        self,
    ) -> tuple[Optional[ActionProposal], Optional[TerminationDecision]]:
        planner_attempts = 0
        parser_retries = 0
        while planner_attempts < self.budget.max_planner_retries:
            if self._abort_requested:
                return None, TerminationDecision(
                    RunStatus.ABORTED,
                    TerminationReason.EXPLICIT_ABORT,
                    "runtime abort requested",
                )
            try:
                self.tracker.reserve_llm_call("planner")
            except BudgetExceeded:
                return None, TerminationDecision(
                    RunStatus.BUDGET_EXHAUSTED,
                    TerminationReason.MAX_LLM_CALLS,
                    "max_llm_calls reached before planner",
                )
            planner_attempts += 1
            try:
                proposal = self.planner.plan(
                    self.challenge,
                    self.state,
                    self.tool_schemas,
                )
                return proposal, None
            except PlannerOutputError as error:
                parser_retries += 1
                self.state.counters.parser_retries += 1
                logger.warning("Planner output rejected: %s", error)
                if parser_retries >= self.budget.max_parser_retries:
                    return None, TerminationDecision(
                        RunStatus.BLOCKED,
                        TerminationReason.PARSER_RETRY_EXHAUSTED,
                        "parser retry limit reached",
                    )
            except Exception as error:
                logger.warning("Planner request failed: %s", error)

        return None, TerminationDecision(
            RunStatus.BLOCKED,
            TerminationReason.PLANNER_RETRY_EXHAUSTED,
            "planner retry limit reached",
        )

    def _analyze_with_bounds(
        self,
        observation: Observation,
    ) -> tuple[Optional[AnalysisResult], Optional[TerminationDecision]]:
        """Retry Analyzer parsing or transient delivery failures without re-executing Tools."""

        attempts = 0
        while attempts < self.budget.max_parser_retries:
            try:
                self.tracker.reserve_llm_call("analyzer")
                return self.analyzer.analyze(observation, self.state), None
            except PlannerOutputError as error:
                attempts += 1
                self.state.counters.parser_retries += 1
                logger.warning("Analyzer output rejected: %s", error)
            except Exception as error:
                if not self._is_transient_analyzer_error(error):
                    raise
                attempts += 1
                self.state.counters.parser_retries += 1
                logger.warning(
                    "Transient analyzer request failed; retaining captured Tool results: %s",
                    error,
                )
        return None, TerminationDecision(
            RunStatus.BLOCKED,
            TerminationReason.PARSER_RETRY_EXHAUSTED,
            "analyzer retry limit reached; captured Tool observations were preserved",
        )

    @staticmethod
    def _is_transient_analyzer_error(error: Exception) -> bool:
        """Recognize delivery failures while leaving contract/programming errors visible.

        The Analyzer runs after a Tool has already produced auditable artifacts.
        Retrying its remote/model delivery is safe because it cannot re-run the
        Tool action.  Errors that do not look like transport availability
        failures still escape to the normal fatal path for diagnosis.
        """

        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return True
        message = str(error).lower()
        return any(marker in message for marker in (
            "timeout",
            "timed out",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "connection refused",
            "service unavailable",
            "rate limit",
        ))

    @staticmethod
    def _mark_repeated_response(analysis: AnalysisResult) -> AnalysisResult:
        """Retain the Analyzer's text while making duplicate behavior explicit."""

        detail = "Captured response matched an earlier observation; choose a distinct observable before repeating this path."
        recommendations = "\n".join(
            item for item in (analysis.recommendations.strip(), detail) if item
        )
        return AnalysisResult(
            summary=f"{analysis.summary} {detail}",
            outcome=AnalysisOutcome.NO_PROGRESS,
            recommendations=recommendations,
            flag_candidates=analysis.flag_candidates,
            confidence=analysis.confidence,
            knowledge_updates=analysis.knowledge_updates,
        )

    def _finish(self, decision: TerminationDecision) -> RunState:
        self.state.set_termination(decision)
        finalize = getattr(self.checkpoint_handler, "finalize", None)
        if callable(finalize):
            finalize(self.state)
        return self.state
