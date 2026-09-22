from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    Observation,
    RunBudget,
    RunState,
    RunStatus,
    StepRecord,
    TerminationReason,
    ToolCall,
    ToolResult,
)
from agent.runtime.termination import TerminationController


def test_flag_candidate_requires_confirmation_before_solved():
    challenge = ChallengeSpec("c1", "Local", "authorized local challenge")
    state = RunState(challenge)
    state.last_analysis = AnalysisResult(
        "candidate found",
        AnalysisOutcome.PROGRESS,
        flag_candidates=[FlagCandidate("FLAG{X}", "fake", 1.0, "output")],
    )
    controller = TerminationController(RunBudget())

    pending = controller.evaluate(state)
    solved = controller.evaluate(state, flag_confirmer=lambda candidate: True)

    assert pending.status == RunStatus.RUNNING
    assert solved.status == RunStatus.SOLVED
    assert solved.reason == TerminationReason.FLAG_CONFIRMED


def test_descriptive_or_password_values_cannot_finish_an_automatic_run():
    challenge = ChallengeSpec("c1", "Local", "authorized local challenge")
    state = RunState(challenge)
    proposal = ActionProposal("inspect", "read a script", [ToolCall("call-1", "fake", {})])
    result = ToolResult(
        "call-1",
        "fake",
        True,
        stdout='const CORRECT_PASSWORD = "rosebud";',
    )
    observation = Observation(1, proposal.objective, proposal, [result])
    now = datetime.now(timezone.utc)
    analysis = AnalysisResult(
        "password assignment observed",
        AnalysisOutcome.PROGRESS,
        flag_candidates=[
            FlagCandidate("The complete string literal assigned to CORRECT_PASSWORD", "script", 0.99, "description"),
            FlagCandidate("rosebud", "script", 0.99, "password assignment"),
        ],
    )
    state.record_step(StepRecord(1, proposal, [result], observation, analysis, now, now))

    decision = TerminationController(RunBudget()).evaluate(
        state,
        flag_confirmer=lambda candidate: True,
    )

    assert decision.status == RunStatus.RUNNING


def test_resumed_run_gets_a_new_identity_and_records_its_parent():
    state = RunState(
        ChallengeSpec("c1", "Local", "authorized local challenge"),
        run_id="first-run",
        status=RunStatus.ABORTED,
    )

    parent = state.fork_for_resume()

    assert parent == "first-run"
    assert state.parent_run_id == "first-run"
    assert state.run_id != "first-run"
    assert state.status is RunStatus.CREATED
    assert state.termination is None
from datetime import datetime, timezone
