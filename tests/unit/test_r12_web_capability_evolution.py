from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent.completion.experience import (
    ExperienceCandidateCatalog,
    ExperienceCandidateExtractor,
    ExperienceCandidateStore,
)
from agent.completion.models import ChallengeReport, ExperienceReviewStatus
from agent.domains.web.artifacts import RequestArtifact, ResponseArtifact
from agent.domains.web.benchmark import WebBenchmarkLoader, WebBenchmarkRunner
from agent.domains.web.intelligence.manager import WebIntelligenceManager
from agent.domains.web.intelligence.response import WebResponseIntelligenceAnalyzer
from agent.domains.web.research.context import WebResearchContextBuilder
from agent.domains.web.research.experiments import WebExperimentCatalog
from agent.domains.web.research.knowledge import WebKnowledgeModelEnhancer
from agent.domains.web.research.models import (
    WebApplicationModel,
    WebEvidenceType,
    WebExperimentType,
)
from agent.domains.web.state import WebRuntimeState
from agent.experience.store import ExperienceStore
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import ChallengeSpec, RunState
from cli.app import app


runner = CliRunner()
BENCHMARK_ROOT = Path(__file__).resolve().parents[2] / "benchmarks" / "web"


def _request(request_id: str, *, method: str = "GET", url: str, body: str | None = None):
    return RequestArtifact(
        "RequestArtifact",
        request_id,
        method,
        url,
        {},
        {},
        body,
        1.0,
    )


def _response(request_id: str, *, url: str, status: int, content_type: str, body: str):
    return ResponseArtifact(
        "ResponseArtifact",
        request_id,
        url,
        status,
        "",
        [("Content-Type", content_type)],
        body,
        "utf-8",
        False,
    )


def test_response_intelligence_understands_json_error_and_state_differences():
    analyzer = WebResponseIntelligenceAnalyzer()
    first = analyzer.analyze(
        _response(
            "response-1",
            url="http://localhost/api/account?id=1",
            status=403,
            content_type="application/json",
            body='{"error":"forbidden","state":"anonymous"}',
        ),
        _request("response-1", url="http://localhost/api/account?id=1"),
    )
    second = analyzer.analyze(
        _response(
            "response-2",
            url="http://localhost/api/account?id=2",
            status=200,
            content_type="application/json",
            body='{"state":"authenticated","profile":{"role":"member"}}',
        ),
        _request("response-2", url="http://localhost/api/account?id=2"),
    )
    difference = analyzer.compare(first, second)

    assert first.response_format == "JSON"
    assert "authorization_error" in first.error_patterns
    assert dict(first.parameter_shapes)["id"] == "integer"
    assert "profile.role" in second.json_keys
    assert difference.status_changed
    assert difference.state_markers_added == ("authenticated",)


def test_response_intelligence_uses_full_body_digest_and_finds_tail_flag():
    analyzer = WebResponseIntelligenceAnalyzer()
    shared_prefix = "<html><style>" + ("x" * 5_000) + "</style>"
    first = analyzer.analyze(
        _response(
            "long-1", url="http://localhost/", status=200,
            content_type="text/html", body=shared_prefix + "no answer</html>",
        )
    )
    second = analyzer.analyze(
        _response(
            "long-2", url="http://localhost/", status=200,
            content_type="text/html", body=shared_prefix + "moectf{tail-answer}</html>",
        )
    )

    assert first.body_complete is True
    assert first.body_sha256 != second.body_sha256
    assert second.flag_candidates == ("moectf{tail-answer}",)
    assert "flag_candidate" in second.content_signals


def test_web_knowledge_model_tracks_semantics_auth_transition_and_checkpoint(tmp_path):
    requests = [
        _request("state-1", url="http://localhost/login"),
        _request(
            "state-2",
            method="POST",
            url="http://localhost/login",
            body='{"username":"student","quantity":2}',
        ),
    ]
    responses = [
        _response(
            "state-1", url="http://localhost/login", status=200,
            content_type="application/json", body='{"state":"anonymous"}',
        ),
        _response(
            "state-2", url="http://localhost/login", status=200,
            content_type="application/json", body='{"state":"authenticated","status":"updated"}',
        ),
    ]
    intelligence = WebIntelligenceManager().analyze(responses, requests=requests)
    model = WebApplicationModel()
    enhancer = WebKnowledgeModelEnhancer()
    for profile, request in zip(intelligence.response_profiles, requests):
        enhancer.ingest_profile(model, profile, artifact_refs=["artifact-local"], method=request.method)
    for difference in intelligence.state_differences:
        enhancer.ingest_difference(model, difference, artifact_refs=["artifact-local"])
    state = WebRuntimeState(
        domain="web",
        phase="RECON",
        challenge_id="r12-model",
        application_model=model,
    )
    challenge = ChallengeSpec(
        "r12-model",
        "R12 model checkpoint",
        "Fake-local Web knowledge checkpoint",
        category="web",
        authorization_scope="authorized_local_demo",
    )
    checkpoint = IntelligenceCheckpoint(tmp_path / "checkpoint")
    checkpoint.save(
        RunState(challenge, run_id="run-r12-model"),
        IntelligenceStore.create(challenge.challenge_id),
        domain_runtime_state=state,
    )
    restored = checkpoint.load().domain_runtime_state

    assert isinstance(restored, WebRuntimeState)
    roles = {item.name: item.semantic_roles for item in restored.application_model.parameters}
    assert roles["username"] == ["identity"]
    assert roles["quantity"] == ["business"]
    assert restored.application_model.authentication.login_endpoints == ["/login"]
    assert restored.application_model.state_transitions[0].from_state == "anonymous"
    assert restored.application_model.state_transitions[0].to_state == "authenticated"
    assert restored.application_model.user_controlled_inputs
    assert restored.application_model.response_profiles


def test_web_experiment_catalog_has_all_r12_contracts_and_context():
    catalog = WebExperimentCatalog()
    required = {
        WebExperimentType.INPUT_BEHAVIOR_ANALYSIS,
        WebExperimentType.AUTHENTICATION_ANALYSIS,
        WebExperimentType.AUTHORIZATION_ANALYSIS,
        WebExperimentType.FILE_PROCESSING_ANALYSIS,
        WebExperimentType.PARSER_BEHAVIOR_ANALYSIS,
        WebExperimentType.BUSINESS_LOGIC_ANALYSIS,
    }
    assert required <= set(catalog.DEFINITIONS)
    for experiment_type in required:
        proposal = catalog.DEFINITIONS[experiment_type].proposal(
            subject="fake local subject",
            statement="A bounded behavior should be characterized.",
            confidence=0.5,
            priority="MEDIUM",
            evidence_value=0.6,
        )
        assert proposal["goal"]
        assert proposal["context"]["research_question"]
        assert proposal["expected_result"]
        assert proposal["evidence_type"] in {item.value for item in WebEvidenceType}
        assert "tool" not in proposal and "payload" not in proposal


def test_web_research_context_contains_bounded_r12_knowledge():
    state = WebRuntimeState(domain="web", phase="ANALYSIS", challenge_id="r12-context")
    state.application_model.record_parameter_semantics(
        "file",
        endpoint="/upload",
        method="POST",
        location="request",
        semantic_role="file",
        value_shape="path-like",
        artifact_refs=["artifact-upload"],
    )
    context = WebResearchContextBuilder(item_limit=2).build(state)

    parameter = context["application_model"]["parameters"][0]
    assert parameter["semantic_roles"] == ["file"]
    assert parameter["user_controlled"] is True
    assert context["boundary"].startswith("Context is evidence only")


def test_web_research_context_retains_observed_client_request_contract():
    intelligence = WebIntelligenceManager().analyze([
        _response(
            "contract-1", url="http://localhost/", status=200,
            content_type="text/html",
            body=(
                "<script>fetch('/test?level=B', {method: 'POST', "
                "body: JSON.stringify({manifestation: 'none'})})</script>"
            ),
        )
    ])
    state = WebRuntimeState(domain="web", phase="ANALYSIS", challenge_id="contract-context")
    enhancer = WebKnowledgeModelEnhancer()
    enhancer.ingest_profile(
        state.application_model,
        intelligence.response_profiles[0],
        artifact_refs=["artifact-contract"],
    )
    context = WebResearchContextBuilder(item_limit=2).build(state)

    contract = context["application_model"]["response_profiles"][0]["client_requests"][0]
    endpoints = {item["path"]: item for item in context["application_model"]["endpoints"]}
    assert contract["method"] == "POST"
    assert contract["query"] == [["level", "B"]]
    assert contract["json_body"] == [["manifestation", "none"]]
    assert endpoints["/test"]["methods"] == ["POST"]


def test_all_fake_local_web_benchmarks_pass_and_write_result(tmp_path):
    loader = WebBenchmarkLoader(BENCHMARK_ROOT)
    cases = loader.list()
    results = [WebBenchmarkRunner(loader).run(case, result_root=tmp_path) for case in cases]

    assert {
        "authentication", "business_logic", "parameter_behavior", "state_transition",
    } <= {item.benchmark_id for item in results}
    assert all(item.passed for item in results)
    for item in results:
        payload = json.loads((tmp_path / f"{item.benchmark_id}.json").read_text())
        assert payload["status"] == "PASS"
        assert payload["checks"]


def test_web_benchmark_loader_rejects_escape():
    loader = WebBenchmarkLoader(BENCHMARK_ROOT)
    with pytest.raises(ValueError, match="escapes"):
        loader.load("../outside")


def test_web_completion_extracts_reviewed_success_and_failure_experience(tmp_path):
    report = ChallengeReport(
        challenge_id="r12-review",
        summary="A Web research run completed.",
        domain="web",
        status="COMPLETED",
        key_findings=({
            "title": "Parser error response",
            "description": "A parser error was captured as evidence.",
        },),
        experiments=({
            "goal": "characterize parser error behavior",
            "expected_result": "parser structure recorded",
            "actual_result": "no discriminating difference",
            "status": "FAILED",
        },),
        artifacts=(),
        evidence=({"source": "fake local", "observation": "parser error evidence"},),
    )
    candidates = ExperienceCandidateExtractor().extract(report)
    categories = {item.category for item in candidates}
    assert "parser_behavior" in categories
    assert "web_failed_experiment" in categories

    challenge_root = tmp_path / "challenges"
    store = ExperienceCandidateStore(
        challenge_root / report.challenge_id / "experience_candidates.json",
        challenge_id=report.challenge_id,
    )
    store.replace_all(candidates)
    global_path = tmp_path / "global" / "experience.json"
    catalog = ExperienceCandidateCatalog(challenge_root, global_path)
    approved = catalog.approve(candidates[0].id)
    rejected = catalog.reject(candidates[1].id)

    assert approved.review_status is ExperienceReviewStatus.APPROVED
    assert rejected.review_status is ExperienceReviewStatus.REJECTED
    memories = ExperienceStore(global_path).list()
    assert len(memories) == 1
    assert memories[0].domain == "web"


def test_web_benchmark_cli_lists_and_runs_fake_local_case(tmp_path):
    listed = runner.invoke(app, ["web", "benchmark", "--root", str(BENCHMARK_ROOT)])
    executed = runner.invoke(app, [
        "web", "benchmark", "authentication",
        "--root", str(BENCHMARK_ROOT),
        "--result-dir", str(tmp_path),
    ])

    assert listed.exit_code == 0
    assert "authentication" in listed.stdout
    assert executed.exit_code == 0
    assert "Result: PASS" in executed.stdout
    assert (tmp_path / "authentication.json").is_file()
