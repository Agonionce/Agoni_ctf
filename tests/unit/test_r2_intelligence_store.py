from __future__ import annotations

from agent.intelligence.models import (
    AttackSurface,
    ArtifactReference,
    Confidence,
    Credential,
    FailedAttempt,
    Fact,
    Finding,
    Hypothesis,
    HypothesisStatus,
    OpenQuestion,
    OpenQuestionStatus,
    Priority,
)
from agent.intelligence.retriever import IntelligenceRetriever
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import ChallengeSpec, RunState
from agent.runtime.planner import JsonPlanner


def test_store_crud_query_serialization_and_artifact_links(tmp_path):
    store = IntelligenceStore.create("web-demo")
    fact = store.add_fact(
        Fact(
            category="endpoint",
            content="/admin returns 200",
            confidence=Confidence.MEDIUM,
            source_step=1,
            artifact_refs=[ArtifactReference("artifact-001", "evidence_for")],
        )
    )
    store.update_fact(fact.id, confidence=Confidence.CONFIRMED)
    hypothesis = store.add_hypothesis(Hypothesis("/admin has SQL injection"))
    store.update_hypothesis(hypothesis.id, status=HypothesisStatus.SUPPORTED)
    assert store.get_hypothesis(hypothesis.id).status is HypothesisStatus.SUPPORTED
    store.update_hypothesis(hypothesis.id, status=HypothesisStatus.REJECTED)
    attempt = store.add_failed_attempt(
        FailedAttempt(
            category="sqli",
            target="/admin?id=1",
            method="UNION SELECT",
            input_payload="?id=1 union select 1",
            result="failed",
            reason="keyword filter",
            source_step=2,
        )
    )
    finding = store.add_finding(
        Finding(
            title="Admin endpoint is exposed",
            description="The endpoint exists but needs a bypass investigation.",
            importance=Priority.HIGH,
            related_facts=[fact.id],
            related_artifacts=[ArtifactReference("artifact-001", "evidence_for")],
            source_steps=[1],
        )
    )
    surface = store.add_attack_surface(
        AttackSurface("web", "/admin", "GET", ["id"], source_step=1)
    )
    question = store.add_open_question(OpenQuestion("What bypasses the filter?"))
    store.update_open_question(question.id, status=OpenQuestionStatus.ANSWERED)

    assert store.query_facts(category="endpoint") == [fact]
    assert store.get_fact(fact.id).confidence is Confidence.CONFIRMED
    assert store.query_failed_attempts(keywords=["union", "filter"]) == [attempt]
    assert store.get_hypothesis(hypothesis.id).status is HypothesisStatus.REJECTED
    assert store.get_finding(finding.id) == finding
    assert store.get_attack_surface(surface.id) == surface
    assert store.get_open_question(question.id).status is OpenQuestionStatus.ANSWERED
    assert len(store.state.artifact_links) == 2

    state_path = tmp_path / "intelligence.json"
    store.save(state_path)
    restored = IntelligenceStore.load(state_path)
    assert restored.get_fact(fact.id).content == "/admin returns 200"
    assert restored.get_failed_attempt(attempt.id).reason == "keyword filter"
    assert len(restored.state.artifact_links) == 2


def test_credentials_are_masked_in_safe_views_and_retrieval():
    store = IntelligenceStore.create("credential-demo")
    credential = store.add_credential(
        Credential(
            credential_type="token",
            value="abcd1234secret",
            location="local CTF response",
            source="step-1",
        )
    )

    assert credential.masked_value() == "abcd********"
    safe_state = store.state.to_dict(mask_credentials=True)
    assert safe_state["credentials"][0]["value"] == "abcd********"
    assert "1234secret" not in str(IntelligenceRetriever(store).retrieve("token").to_dict())


def test_retriever_returns_relevant_failures_not_all_state():
    store = IntelligenceStore.create("retriever-demo")
    store.add_fact(Fact("endpoint", "/login accepts username", Confidence.HIGH, 1))
    store.add_fact(Fact("configuration", "archive cipher uses AES", Confidence.HIGH, 1))
    relevant = store.add_failed_attempt(
        FailedAttempt("sqli", "/login", "UNION SELECT", "union select", "failed", "filter", 2)
    )
    store.add_failed_attempt(
        FailedAttempt("crypto", "cipher", "bruteforce", "abc", "failed", "wrong keyspace", 3)
    )

    context = IntelligenceRetriever(store).retrieve("SQL injection UNION /login", categories=["sqli"])

    assert [item["id"] for item in context.failed_attempts] == [relevant.id]
    assert [item["content"] for item in context.facts] == ["/login accepts username"]


def test_json_planner_receives_filtered_intelligence_context():
    challenge = ChallengeSpec("planner-context", "Web challenge", "Inspect /admin endpoint", category="web")
    store = IntelligenceStore.create(challenge.challenge_id)
    store.add_fact(Fact("endpoint", "/admin exists", Confidence.CONFIRMED, 1))
    captured = {}

    def requester(system_prompt, user_prompt):
        captured["user_prompt"] = user_prompt
        return {
            "objective": "inspect local evidence",
            "reasoning_summary": "use registered local tool",
            "actions": [{"tool_name": "file", "arguments": {"path": "chall"}}],
        }

    planner = JsonPlanner(
        requester,
        intelligence_context_provider=lambda current_challenge, state: IntelligenceRetriever(store)
        .retrieve(current_challenge.description, categories=["web"])
        .to_dict(),
    )

    proposal = planner.plan(challenge, RunState(challenge), [])

    assert proposal.actions[0].tool_name == "file"
    assert "/admin exists" in captured["user_prompt"]
