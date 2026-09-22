from agent.runtime.budget import BudgetTracker
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    RunBudget,
    RunState,
    TerminationReason,
    ToolCall,
    ToolResult,
)


def test_runtime_clock_excludes_paused_time_and_enforces_runtime():
    now = [0.0]
    challenge = ChallengeSpec("c1", "Local", "authorized local challenge")
    state = RunState(challenge)
    tracker = BudgetTracker(
        RunBudget(max_runtime=10),
        state.counters,
        clock=lambda: now[0],
    )
    tracker.start()
    now[0] = 5
    tracker.pause()
    now[0] = 100
    tracker.resume()
    now[0] = 104

    assert tracker.elapsed == 9
    assert tracker.pre_step_decision(state) is None
    now[0] = 106
    decision = tracker.pre_step_decision(state)
    assert decision is not None
    assert decision.reason == TerminationReason.MAX_RUNTIME


def test_duplicate_fingerprint_is_counted_by_tool_and_arguments():
    challenge = ChallengeSpec("c1", "Local", "authorized local challenge")
    state = RunState(challenge)
    tracker = BudgetTracker(RunBudget(max_duplicate_actions=2), state.counters)
    proposal = ActionProposal(
        "inspect",
        "repeat",
        [ToolCall("call-1", "fake", {"path": "/tmp/a"})],
    )

    assert tracker.register_actions(state, proposal) is None
    assert tracker.register_actions(state, proposal) is None
    decision = tracker.register_actions(state, proposal)
    assert decision is not None
    assert decision.reason == TerminationReason.DUPLICATE_ACTIONS


def test_failure_counter_resets_on_progress():
    challenge = ChallengeSpec("c1", "Local", "authorized local challenge")
    state = RunState(challenge)
    tracker = BudgetTracker(RunBudget(max_consecutive_failures=3), state.counters)
    tracker.record_outcome(AnalysisOutcome.NO_PROGRESS)
    tracker.record_outcome(AnalysisOutcome.ACTION_FAILED)
    assert state.counters.consecutive_failures == 2
    tracker.record_outcome(AnalysisOutcome.PROGRESS)
    assert state.counters.consecutive_failures == 0


def test_repeated_web_response_is_marked_as_negative_evidence():
    challenge = ChallengeSpec("c1", "Local", "authorized local challenge")
    state = RunState(challenge)
    tracker = BudgetTracker(RunBudget(), state.counters)

    def result(call_id: str) -> ToolResult:
        return ToolResult(
            call_id,
            "http_request",
            True,
            metadata={
                "web_observation": {
                    "status_code": 200,
                    "response_body_preview": "unchanged fake local response",
                }
            },
        )

    assert tracker.register_response_fingerprints(state, [result("first")]) == []
    repeated = result("second")
    assert tracker.register_response_fingerprints(state, [repeated]) == ["second"]
    assert state.counters.repeated_responses == 1
    assert repeated.metadata["response_repeat"]["previous_observations"] == 1


def test_full_response_digest_prevents_long_page_prefix_collisions():
    challenge = ChallengeSpec("c1", "Local", "authorized local challenge")
    state = RunState(challenge)
    tracker = BudgetTracker(RunBudget(), state.counters)

    def result(call_id: str, digest: str) -> ToolResult:
        return ToolResult(
            call_id,
            "http_request",
            True,
            metadata={
                "web_observation": {
                    "status_code": 200,
                    "response_body_preview": "same long page prefix",
                    "response_body_sha256": digest,
                    "response_body_complete": True,
                }
            },
        )

    assert tracker.register_response_fingerprints(state, [result("first", "a" * 64)]) == []
    assert tracker.register_response_fingerprints(state, [result("different-tail", "b" * 64)]) == []
    repeated = result("same-full-body", "a" * 64)
    assert tracker.register_response_fingerprints(state, [repeated]) == ["same-full-body"]
