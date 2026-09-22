from __future__ import annotations

from agent.domains.manager import build_default_runtime_manager
from agent.domains.web.analyzer import WebResponseAnalyzer
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.store import IntelligenceStore
from agent.intelligence.updater import KnowledgeUpdater
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    Observation,
    ToolCall,
    ToolResult,
)
from agent.runtime.integration import challenge_from_question
from ctf_platform.base import Question


def _web_observation() -> Observation:
    proposal = ActionProposal(
        "observe local login",
        "test deterministic Web metadata",
        [ToolCall("http-1", "http_request", {})],
    )
    return Observation(
        step_id=1,
        objective=proposal.objective,
        proposal=proposal,
        tool_results=[
            ToolResult(
                "http-1",
                "http_request",
                True,
                metadata={
                    "web_observation": {
                        "base_url": "http://127.0.0.1:8000",
                        "endpoint": "/login",
                        "parameters": ["username"],
                        "reflected_parameters": ["username"],
                        "status_code": 200,
                        "technologies": ["FakePHP/1.0"],
                        "cookies": {"session": "local-session"},
                    }
                },
                artifact_refs=["artifact-001", "artifact-002", "artifact-003"],
            )
        ],
    )


def test_web_runtime_state_tracks_web_observations_and_masks_cookie_context():
    challenge = ChallengeSpec("r5-state", "Login", "local PHP login", category="web")
    manager = build_default_runtime_manager()
    state = manager.initialize("web", challenge)
    assert isinstance(state, WebRuntimeState)

    manager.route_observation(
        {"summary": "local HTTP response captured", "observation": _web_observation()}
    )
    context = manager.generate_context()

    assert state.base_url == "http://127.0.0.1:8000"
    assert state.endpoints == ["/login"]
    assert state.parameters == {"username": ["/login"]}
    assert state.cookies == {"session": "local-session"}
    assert state.technologies == ["FakePHP/1.0"]
    assert context["state"]["cookies"] == ["session"]
    assert "local-session" not in str(context)
    assert manager.next_phase().phase == "ANALYSIS"


def test_web_response_analyzer_creates_evidence_facts_without_vulnerability_claims():
    observation = _web_observation()
    suggestions = WebResponseAnalyzer().suggestions(observation)
    analysis = AnalysisResult(
        summary="deterministic Web metadata extracted",
        outcome=AnalysisOutcome.PROGRESS,
        knowledge_updates=suggestions,
    )
    store = IntelligenceStore.create("r5-state")

    applied = KnowledgeUpdater(store).apply(analysis, observation)
    contents = [fact.content for fact in store.state.facts]

    assert len(applied.applied_ids) == 5
    assert "endpoint=/login" in contents
    assert "status_code=200 endpoint=/login" in contents
    assert "parameter=username endpoint=/login" in contents
    assert "reflection=username endpoint=/login" in contents
    assert "technology=FakePHP/1.0" in contents
    assert not any("vulnerab" in content.lower() for content in contents)
    assert all(fact.artifact_refs for fact in store.state.facts)


def test_question_url_becomes_declared_web_base_url_without_mutating_metadata():
    metadata = {"category": "web"}

    challenge = challenge_from_question(
        Question(
            "Local Web",
            "authorized local target",
            url="http://127.0.0.1:8080/",
            metadata=metadata,
        )
    )

    assert challenge.metadata["base_url"] == "http://127.0.0.1:8080/"
    assert "base_url" not in metadata
