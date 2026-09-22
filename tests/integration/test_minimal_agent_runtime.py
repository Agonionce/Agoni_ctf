from __future__ import annotations

from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    RunBudget,
    RunStatus,
    TerminationReason,
    ToolCall,
    ToolResult,
)
from agent.runtime.errors import PlannerOutputError
from agent.runtime.runtime import AgentRuntime


class FakePlanner:
    def __init__(self, invalid=False):
        self.invalid = invalid
        self.calls = 0

    def plan(self, challenge, state, tool_schemas):
        self.calls += 1
        if self.invalid:
            raise PlannerOutputError("deterministic invalid planner output")
        return ActionProposal(
            objective="read deterministic local flag",
            reasoning_summary="use one fake local tool",
            actions=[ToolCall("call-1", "fake_tool", {})],
        )


class FakeExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, proposal):
        self.calls += 1
        return [
            ToolResult(
                call_id=proposal.actions[0].call_id,
                tool_name="fake_tool",
                success=True,
                stdout="FLAG{LOCAL_AGENT_LOOP_OK}",
            )
        ]


class FakeAnalyzer:
    def analyze(self, observation, state):
        return AnalysisResult(
            summary="the fake tool returned a flag candidate",
            outcome=AnalysisOutcome.PROGRESS,
            flag_candidates=[
                FlagCandidate(
                    "FLAG{LOCAL_AGENT_LOOP_OK}",
                    "fake_tool.stdout",
                    1.0,
                    observation.tool_results[0].stdout,
                )
            ],
            confidence=1.0,
        )


class SequencePlanner:
    def __init__(self):
        self.calls = 0

    def plan(self, challenge, state, tool_schemas):
        self.calls += 1
        return ActionProposal(
            objective="make bounded progress",
            reasoning_summary="unique deterministic action",
            actions=[
                ToolCall(
                    f"call-{self.calls}",
                    "fake_tool",
                    {"step": self.calls},
                )
            ],
        )


class OutcomeAnalyzer:
    def __init__(self, outcome):
        self.outcome = outcome

    def analyze(self, observation, state):
        return AnalysisResult("deterministic outcome", self.outcome)


class EmptyExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, proposal):
        self.calls += 1
        return [
            ToolResult(
                call_id=proposal.actions[0].call_id,
                tool_name="fake_tool",
                success=True,
                stdout="no flag",
            )
        ]


class InvalidAnalyzer:
    def __init__(self):
        self.calls = 0

    def analyze(self, observation, state):
        self.calls += 1
        raise PlannerOutputError("deterministic invalid analyzer output")


class TransientAnalyzer:
    def __init__(self):
        self.calls = 0

    def analyze(self, _observation, _state):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("model request timed out")
        return AnalysisResult("analysis recovered without another tool action", AnalysisOutcome.PROGRESS)


def test_deterministic_r0_runtime_solves_without_network_or_shell():
    challenge = ChallengeSpec(
        challenge_id="local-demo",
        title="R0 local demo",
        description="deterministic authorized local test",
    )
    runtime = AgentRuntime(
        challenge=challenge,
        planner=FakePlanner(),
        executor=FakeExecutor(),
        analyzer=FakeAnalyzer(),
        budget=RunBudget(max_steps=100, max_llm_calls=250),
        flag_confirmer=lambda candidate: candidate.value
        == "FLAG{LOCAL_AGENT_LOOP_OK}",
    )

    state = runtime.run()

    assert state.status == RunStatus.SOLVED
    assert state.termination is not None
    assert state.termination.flag_candidate is not None
    assert state.termination.flag_candidate.value == "FLAG{LOCAL_AGENT_LOOP_OK}"
    assert len(state.steps) == 1
    assert state.counters.step_count == 1
    assert state.counters.llm_calls == 2


def test_parser_retry_is_bounded():
    challenge = ChallengeSpec("local-invalid", "Invalid", "local test")
    planner = FakePlanner(invalid=True)
    runtime = AgentRuntime(
        challenge=challenge,
        planner=planner,
        executor=FakeExecutor(),
        analyzer=FakeAnalyzer(),
        budget=RunBudget(max_planner_retries=8, max_parser_retries=3),
    )

    state = runtime.run()

    assert state.status == RunStatus.BLOCKED
    assert state.termination is not None
    assert state.termination.reason == TerminationReason.PARSER_RETRY_EXHAUSTED
    assert planner.calls == 3


def test_max_steps_is_a_hard_runtime_boundary():
    challenge = ChallengeSpec("local-steps", "Steps", "local test")
    runtime = AgentRuntime(
        challenge=challenge,
        planner=SequencePlanner(),
        executor=EmptyExecutor(),
        analyzer=OutcomeAnalyzer(AnalysisOutcome.PROGRESS),
        budget=RunBudget(max_steps=2),
    )

    state = runtime.run()

    assert state.status == RunStatus.BUDGET_EXHAUSTED
    assert state.termination.reason == TerminationReason.MAX_STEPS
    assert len(state.steps) == 2


def test_max_llm_calls_stops_after_accounted_planner_and_analyzer():
    challenge = ChallengeSpec("local-llm", "LLM", "local test")
    runtime = AgentRuntime(
        challenge=challenge,
        planner=SequencePlanner(),
        executor=EmptyExecutor(),
        analyzer=OutcomeAnalyzer(AnalysisOutcome.PROGRESS),
        budget=RunBudget(max_llm_calls=2),
    )

    state = runtime.run()

    assert state.status == RunStatus.BUDGET_EXHAUSTED
    assert state.termination.reason == TerminationReason.MAX_LLM_CALLS
    assert state.counters.llm_calls == 2


def test_consecutive_failures_block_and_progress_resets_counter():
    challenge = ChallengeSpec("local-failures", "Failures", "local test")
    runtime = AgentRuntime(
        challenge=challenge,
        planner=SequencePlanner(),
        executor=EmptyExecutor(),
        analyzer=OutcomeAnalyzer(AnalysisOutcome.NO_PROGRESS),
        budget=RunBudget(max_consecutive_failures=3),
    )

    state = runtime.run()

    assert state.status == RunStatus.BLOCKED
    assert state.termination.reason == TerminationReason.CONSECUTIVE_FAILURES
    assert state.counters.consecutive_failures == 3


def test_analyzer_parser_retry_is_bounded_without_reexecuting_tools():
    challenge = ChallengeSpec("local-analyzer-invalid", "Analyzer", "local test")
    executor = EmptyExecutor()
    analyzer = InvalidAnalyzer()
    runtime = AgentRuntime(
        challenge=challenge,
        planner=SequencePlanner(),
        executor=executor,
        analyzer=analyzer,
        budget=RunBudget(max_parser_retries=2),
    )

    state = runtime.run()

    assert state.status == RunStatus.BLOCKED
    assert state.termination.reason == TerminationReason.PARSER_RETRY_EXHAUSTED
    assert analyzer.calls == 2
    assert executor.calls == 1


def test_transient_analyzer_timeout_retries_without_reexecuting_tools():
    challenge = ChallengeSpec("local-analyzer-timeout", "Analyzer", "local test")
    executor = EmptyExecutor()
    analyzer = TransientAnalyzer()
    runtime = AgentRuntime(
        challenge=challenge,
        planner=SequencePlanner(),
        executor=executor,
        analyzer=analyzer,
        budget=RunBudget(max_steps=1, max_parser_retries=2),
    )

    state = runtime.run()

    assert state.status is RunStatus.BUDGET_EXHAUSTED
    assert state.termination.reason is TerminationReason.MAX_STEPS
    assert analyzer.calls == 2
    assert executor.calls == 1
