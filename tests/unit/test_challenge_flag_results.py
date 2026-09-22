from __future__ import annotations

import json
from datetime import datetime, timezone

from agent.challenge.results import ChallengeFlagResultResolver
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    Observation,
    RunState,
    RunStatus,
    StepRecord,
    TerminationDecision,
    TerminationReason,
    ToolCall,
    ToolResult,
)


def _solved_state(challenge: ChallengeSpec, candidate: FlagCandidate, observed: str) -> RunState:
    state = RunState(challenge)
    proposal = ActionProposal("inspect local evidence", "one bounded read", [ToolCall("call-1", "fake", {})])
    result = ToolResult(
        "call-1",
        "fake",
        True,
        stdout=observed,
        artifact_refs=["artifact-001"],
    )
    observation = Observation(1, proposal.objective, proposal, [result])
    analysis = AnalysisResult(
        "captured local evidence",
        AnalysisOutcome.PROGRESS,
        flag_candidates=[candidate],
    )
    now = datetime.now(timezone.utc)
    state.record_step(StepRecord(1, proposal, [result], observation, analysis, now, now))
    state.set_termination(
        TerminationDecision(
            RunStatus.SOLVED,
            TerminationReason.FLAG_CONFIRMED,
            "historical completion",
            candidate,
        )
    )
    return state


def _write_run(root, number: int, state: RunState) -> None:
    run = root / f"run-{number:03d}"
    (run / "artifacts").mkdir(parents=True)
    (run / "run.json").write_text(
        json.dumps(state.to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )
    (run / "artifacts" / "manifest.json").write_text(
        json.dumps(
            [{"artifact_id": "artifact-001", "path": f"output/response-{number}.json"}]
        ),
        encoding="utf-8",
    )


def test_canonical_result_keeps_evidence_bound_flag_when_later_run_is_prose(tmp_path):
    challenge = ChallengeSpec("challenge-local", "Local", "authorized local fixture")
    first = _solved_state(
        challenge,
        FlagCandidate("FLAG{evidence-bound}", "captured response", 0.92, "response contains FLAG{evidence-bound}"),
        "<div class=flag>FLAG{evidence-bound}</div>",
    )
    later = _solved_state(
        challenge,
        FlagCandidate(
            "The complete string literal assigned to CORRECT_PASSWORD",
            "captured script",
            0.99,
            "a password assignment was observed",
        ),
        'const CORRECT_PASSWORD = "not-a-flag";',
    )
    _write_run(tmp_path, 1, first)
    _write_run(tmp_path, 2, later)

    result = ChallengeFlagResultResolver().resolve(challenge.challenge_id, tmp_path)

    assert result.status == "FOUND"
    assert result.value == "FLAG{evidence-bound}"
    assert result.run_number == 1
    assert result.evidence_paths == ("output/response-1.json",)
