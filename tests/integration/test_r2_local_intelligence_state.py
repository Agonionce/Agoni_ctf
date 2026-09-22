"""R2 local intelligence demo with fake observations only; no network or Shell."""

from __future__ import annotations

from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.models import ArtifactReference, KnowledgeUpdateSuggestion
from agent.intelligence.retriever import IntelligenceRetriever
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    RunBudget,
    RunStatus,
    ToolCall,
    ToolResult,
)
from agent.runtime.runtime import AgentRuntime


class DemoPlanner:
    def plan(self, challenge, state, tool_schemas):
        if state.current_step == 0:
            return ActionProposal(
                "record the local admin observation",
                "capture the deterministic fake endpoint evidence",
                [ToolCall("discover-admin", "fake_observe", {})],
            )
        return ActionProposal(
            "record the failed deterministic SQLi route",
            "avoid repeating the same filtered UNION route",
            [ToolCall("attempt-union", "fake_attempt", {"payload": "union select"})],
        )


class DemoExecutor:
    def execute(self, proposal):
        action = proposal.actions[0]
        if action.tool_name == "fake_observe":
            return [ToolResult(action.call_id, action.tool_name, True, stdout="/admin exists")]
        return [
            ToolResult(
                action.call_id,
                action.tool_name,
                False,
                stdout="blocked LOCAL_INTELLIGENCE_STATE_OK",
                error="keyword filter",
            )
        ]


class DemoAnalyzer:
    def analyze(self, observation, state):
        if observation.step_id == 1:
            return AnalysisResult(
                summary="fake evidence confirms /admin exists",
                outcome=AnalysisOutcome.PROGRESS,
                knowledge_updates=[
                    KnowledgeUpdateSuggestion(
                        kind="fact",
                        payload={
                            "category": "endpoint",
                            "content": "/admin exists",
                            "confidence": "CONFIRMED",
                        },
                        artifact_refs=[ArtifactReference("artifact-001", "evidence_for")],
                    )
                ],
            )
        return AnalysisResult(
            summary="the UNION route is confirmed filtered",
            outcome=AnalysisOutcome.ACTION_FAILED,
            flag_candidates=[
                FlagCandidate(
                    "LOCAL_INTELLIGENCE_STATE_OK",
                    "local intelligence demo",
                    1.0,
                    "fact and failed attempt persisted",
                )
            ],
            knowledge_updates=[
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
                )
            ],
        )


def test_local_intelligence_state_survives_checkpoint_resume(tmp_path):
    challenge = ChallengeSpec(
        challenge_id="r2-local-web-demo",
        title="Fake web challenge",
        description="Authorized deterministic local web challenge",
        category="web",
    )
    intelligence = IntelligenceStore.create(challenge.challenge_id)
    runtime = AgentRuntime(
        challenge=challenge,
        planner=DemoPlanner(),
        executor=DemoExecutor(),
        analyzer=DemoAnalyzer(),
        budget=RunBudget(max_steps=3, max_llm_calls=10),
        intelligence_store=intelligence,
        flag_confirmer=lambda candidate: candidate.value == "LOCAL_INTELLIGENCE_STATE_OK",
    )

    state = runtime.run()
    checkpoint = IntelligenceCheckpoint(tmp_path / "r2_local_demo")
    checkpoint.save(
        state,
        intelligence,
        [{"artifact_id": "artifact-001", "path": "work/local-observation.txt"}],
    )
    resumed = checkpoint.load()
    context = IntelligenceRetriever(resumed.intelligence_store).retrieve(
        "SQL injection union admin",
        categories=["sqli"],
    )

    assert state.status is RunStatus.SOLVED
    assert state.termination is not None
    assert state.termination.flag_candidate is not None
    assert state.termination.flag_candidate.value == "LOCAL_INTELLIGENCE_STATE_OK"
    assert resumed.intelligence_store.state.facts[0].content == "/admin exists"
    assert resumed.intelligence_store.state.failed_attempts[0].method == "UNION SELECT"
    assert context.failed_attempts[0]["reason"] == "keyword filter"
    assert resumed.artifacts[0]["artifact_id"] == "artifact-001"
