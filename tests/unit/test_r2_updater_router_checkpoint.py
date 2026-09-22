from __future__ import annotations

from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.models import (
    ArtifactReference,
    FailedAttempt,
    KnowledgeUpdateSuggestion,
)
from agent.intelligence.router import SkillRouter
from agent.intelligence.store import IntelligenceStore
from agent.intelligence.updater import KnowledgeUpdater
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    Observation,
    RunState,
    ToolCall,
    ToolResult,
)


def _observation(step_id: int = 1) -> Observation:
    proposal = ActionProposal("inspect local evidence", "test updater", [ToolCall("call-1", "fake", {})])
    return Observation(
        step_id=step_id,
        objective=proposal.objective,
        proposal=proposal,
        tool_results=[ToolResult("call-1", "fake", True, stdout="/admin exists")],
    )


def test_knowledge_updater_applies_analyzer_suggestions_only_after_analysis():
    store = IntelligenceStore.create("updater-demo")
    analysis = AnalysisResult(
        summary="observed an admin endpoint and one filtered SQLi attempt",
        outcome=AnalysisOutcome.PARTIAL_SUCCESS,
        knowledge_updates=[
            KnowledgeUpdateSuggestion(
                kind="fact",
                payload={
                    "category": "endpoint",
                    "content": "/admin exists",
                    "confidence": "CONFIRMED",
                },
                artifact_refs=[ArtifactReference("artifact-001", "evidence_for")],
            ),
            KnowledgeUpdateSuggestion(
                kind="failed_attempt",
                payload={
                    "category": "sqli",
                    "target": "/admin?id=1",
                    "method": "UNION SELECT",
                    "input_payload": "?id=1 union select 1",
                    "result": "failed",
                    "reason": "keyword filter",
                },
            ),
        ],
    )

    applied = KnowledgeUpdater(store).apply(analysis, _observation(step_id=7))

    assert len(applied.applied_ids) == 2
    assert not applied.rejected
    assert store.state.facts[0].source_step == 7
    assert store.state.failed_attempts[0].method == "UNION SELECT"


def test_checkpoint_v2_restores_run_state_intelligence_and_artifact_metadata(tmp_path):
    challenge = ChallengeSpec("checkpoint-demo", "Web CTF", "http endpoint with SQL injection")
    run_state = RunState(challenge)
    store = IntelligenceStore.create(challenge.challenge_id)
    fact_result = KnowledgeUpdater(store).apply(
        AnalysisResult(
            summary="fact", outcome=AnalysisOutcome.PROGRESS,
            knowledge_updates=[
                KnowledgeUpdateSuggestion(
                    kind="fact",
                    payload={"category": "endpoint", "content": "/admin exists"},
                )
            ],
        ),
        _observation(),
    )
    assert fact_result.applied_ids
    store.add_failed_attempt(
        FailedAttempt(
            "sqli",
            "/admin",
            "UNION SELECT",
            "union",
            "failed",
            "filter",
            2,
            [ArtifactReference("artifact-001", "evidence_for")],
        )
    )
    checkpoint = IntelligenceCheckpoint(tmp_path / "r2_demo")
    checkpoint.save(
        run_state,
        store,
        [{"artifact_id": "artifact-001", "path": "work/response.txt"}],
    )

    restored = checkpoint.load()

    assert restored.run_state.challenge.challenge_id == "checkpoint-demo"
    assert restored.intelligence_store.state.facts[0].content == "/admin exists"
    assert restored.intelligence_store.state.failed_attempts[0].method == "UNION SELECT"
    assert restored.artifacts[0]["artifact_id"] == "artifact-001"
    assert {path.name for path in (tmp_path / "r2_demo").iterdir()} == {
        "run.json", "intelligence.json", "artifacts.json", "experiments.json"
    }


def test_skill_router_classifies_web_and_pwn_challenges():
    router = SkillRouter()
    web = router.route(ChallengeSpec("web", "Login", "http://ctf.local/login cookie SQL injection"))
    pwn = router.route(ChallengeSpec("pwn", "ELF service", "amd64 ELF, run checksec then connect with nc"))

    assert web.primary_skill == "web"
    assert pwn.primary_skill == "pwn"
