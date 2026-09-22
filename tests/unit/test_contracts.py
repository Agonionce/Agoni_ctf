from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    RunBudget,
    RunState,
    ToolCall,
)


def test_core_contracts_are_typed_and_duplicate_fingerprint_is_stable():
    challenge = ChallengeSpec(
        challenge_id="local-1",
        title="Local challenge",
        description="Authorized local lab",
    )
    state = RunState(challenge=challenge)
    first = ToolCall("call-a", "fake_tool", {"b": 2, "a": 1})
    second = ToolCall("call-b", "fake_tool", {"a": 1, "b": 2})
    proposal = ActionProposal("inspect", "short rationale", [first])
    result = AnalysisResult(
        summary="progress",
        outcome=AnalysisOutcome.PROGRESS,
        flag_candidates=[
            FlagCandidate("FLAG{X}", "fake_tool", 0.9, "explicit output")
        ],
    )

    assert first.fingerprint() == second.fingerprint()
    assert proposal.actions[0].tool_name == "fake_tool"
    assert result.flag_candidates[0].value == "FLAG{X}"
    assert state.to_dict()["status"] == "CREATED"
    assert RunBudget().validate().max_steps == 100
