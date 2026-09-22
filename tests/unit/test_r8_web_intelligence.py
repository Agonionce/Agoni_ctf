from __future__ import annotations

import json

from typer.testing import CliRunner

from agent.artifacts.store import ArtifactStore
from agent.domains.manager import build_default_runtime_manager
from agent.domains.web.analyzer import WebIntelligenceAnalyzer, WebResponseAnalyzer
from agent.domains.web.artifacts import RequestArtifact, ResponseArtifact, SessionArtifact
from agent.domains.web.intelligence.behavior import ResponseBehaviorAnalyzer
from agent.domains.web.intelligence.context import WebAttackSurfaceContextBuilder
from agent.domains.web.intelligence.endpoint_mapper import EndpointMapper
from agent.domains.web.intelligence.html_analyzer import HTMLAnalyzer
from agent.domains.web.intelligence.manager import WebIntelligenceManager
from agent.domains.web.intelligence.models import WebAttackSurface
from agent.domains.web.intelligence.technology import TechnologyDetector
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.models import Confidence, EndpointFinding
from agent.intelligence.store import IntelligenceStore
from agent.intelligence.updater import KnowledgeUpdater
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyEngine
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
from agent.runtime.planner import JsonPlanner
from agent.tools.contracts import ExecutionContext
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime
from agent.tools.web_intelligence import WebIntelligenceTool
from agent.workspace.manager import WorkspaceManager
from cli.app import app


runner = CliRunner()


def _response(
    request_id: str = "request-001",
    *,
    url: str = "http://127.0.0.1:8000/",
    body: str = "",
    headers: list[tuple[str, str]] | None = None,
) -> ResponseArtifact:
    return ResponseArtifact(
        artifact_kind="ResponseArtifact",
        request_id=request_id,
        url=url,
        status_code=200,
        reason="OK",
        headers=headers or [("Content-Type", "text/html")],
        body=body,
        body_encoding="utf-8",
        truncated=False,
    )


def _request(
    request_id: str,
    url: str,
    parameters: dict[str, str] | None = None,
) -> RequestArtifact:
    return RequestArtifact(
        artifact_kind="RequestArtifact",
        request_id=request_id,
        method="GET",
        url=url,
        headers={},
        parameters=parameters or {},
        body=None,
        timeout=2.0,
    )


def test_html_analyzer_extracts_forms_inputs_links_scripts_and_comments():
    response = _response(
        body="""<html><head><title>Local Login</title></head><body>
        <!-- review local admin route -->
        <form action="/login" method="post">
          <input name="username"><input name="password">
          <select name="role"></select>
        </form>
        <a href="/admin">Admin</a><script src="/static/app.js"></script>
        <script>window.demo = true;</script></body></html>"""
    )

    analysis = HTMLAnalyzer().analyze(response)

    assert analysis.title == "Local Login"
    assert analysis.forms[0].action == "/login"
    assert analysis.forms[0].method == "POST"
    assert analysis.forms[0].inputs == ("password", "role", "username")
    assert analysis.links == ("/admin",)
    assert analysis.scripts == ("/static/app.js", "<inline>")
    assert analysis.comments == ("review local admin route",)


def test_html_analyzer_extracts_literal_inline_fetch_contract_without_execution():
    response = _response(
        body="""<script>
        async function testTalent() {
          return fetch('/test_talent?level=B', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ manifestation: 'none' })
          });
        }
        </script>"""
    )

    analysis = HTMLAnalyzer().analyze(response)
    contract = analysis.client_requests[0]
    surface = EndpointMapper().map([analysis])
    mapped = {(item.path, item.method): item for item in surface.endpoints}

    assert contract.method == "POST"
    assert contract.path == "/test_talent"
    assert contract.query == (("level", "B"),)
    assert contract.json_body == (("manifestation", "none"),)
    assert contract.header_names == ("Content-Type",)
    assert mapped[("/test_talent", "POST")].parameters == [
        "level", "manifestation"
    ]


def test_endpoint_mapper_builds_same_origin_surface_without_probing():
    analysis = HTMLAnalyzer().analyze(
        _response(
            body="""<form action="/login" method="post">
            <input name="username"><input name="password"></form>
            <a href="/article?id=1">Article</a>
            <a href="http://127.0.0.1:9999/outside">Other origin</a>"""
        )
    )
    request = _request(
        "request-002",
        "http://127.0.0.1:8000/article?id=2",
        {"id": "2"},
    )

    surface = EndpointMapper().map([analysis], [request])
    by_identity = {(item.path, item.method): item for item in surface.endpoints}

    assert by_identity[("/login", "POST")].parameters == ["password", "username"]
    assert by_identity[("/article", "GET")].parameters == ["id"]
    assert by_identity[("/article", "GET")].confidence is Confidence.CONFIRMED
    assert not any(item.path == "/outside" for item in surface.endpoints)
    assert surface.parameters == ["id", "password", "username"]


def test_technology_detector_records_header_html_and_cookie_evidence_only():
    response = _response(
        headers=[
            ("Server", "nginx/1.25"),
            ("X-Powered-By", "Flask"),
        ],
        body='<meta name="generator" content="Flask"><p>SQLite message</p>',
    )
    session = SessionArtifact(
        "SessionArtifact",
        "request-001",
        response_cookies={"session": "must-not-appear"},
    )

    evidence = TechnologyDetector().detect(response, session)

    assert {item.technology for item in evidence} >= {"nginx", "Flask", "SQLite"}
    assert all("vulnerab" not in item.evidence.lower() for item in evidence)
    assert "must-not-appear" not in str(evidence)


def test_response_behavior_diff_reports_evidence_not_sqli_confirmation():
    baseline = _response(
        "request-001",
        url="http://127.0.0.1:8000/article?id=1",
        body="<title>Article 1</title>Local article one",
    )
    current = _response(
        "request-002",
        url="http://127.0.0.1:8000/article?id=2",
        body="<title>Error</title>SQLite database error: missing row",
    )

    difference, findings = ResponseBehaviorAnalyzer().compare(baseline, current)

    assert difference.content_changed is True
    assert difference.length_difference != 0
    assert difference.title_changed is True
    assert "sqlite error" in difference.current_errors
    assert findings[0].title == "Possible database-related behavior"
    assert "not confirmation" in findings[0].description


def test_manager_and_analyzer_write_endpoint_finding_finding_and_open_hypothesis():
    responses = [
        _response(
            "request-001",
            url="http://127.0.0.1:8000/article?id=1",
            body="<title>Article</title>one",
        ),
        _response(
            "request-002",
            url="http://127.0.0.1:8000/article?id=2",
            body="<title>Error</title>SQLite database error: missing row",
        ),
    ]
    requests = [
        _request(item.request_id, item.url, {"id": item.request_id[-1]})
        for item in responses
    ]
    state = WebIntelligenceManager().analyze(responses, requests=requests)
    observation = Observation(
        step_id=3,
        objective="analyze captured local artifacts",
        proposal=ActionProposal(
            "analyze captured local artifacts",
            "passive comparison",
            [ToolCall("analysis", "web_intelligence", {})],
        ),
        tool_results=[],
    )
    observation.tool_results.append(
        ToolResult(
            "analysis",
            "web_intelligence",
            True,
            metadata={"web_intelligence": state.to_dict()},
            artifact_refs=["artifact-010"],
        )
    )
    suggestions = WebResponseAnalyzer().suggestions(observation)
    store = IntelligenceStore.create("r8-intelligence")
    applied = KnowledgeUpdater(store).apply(
        AnalysisResult(
            "passive Web evidence",
            AnalysisOutcome.PROGRESS,
            knowledge_updates=suggestions,
        ),
        observation,
    )

    assert not applied.rejected
    assert store.state.endpoint_findings[0].path == "/article"
    assert store.state.endpoint_findings[0].parameters == ["id"]
    assert store.state.findings[0].title == "Possible database-related behavior"
    assert store.state.hypotheses[0].statement == (
        "Parameter id may influence a database query"
    )
    assert store.state.hypotheses[0].status.value == "OPEN"
    assert all(item.artifact_refs for item in store.state.endpoint_findings)


def test_web_analyzer_promotes_full_response_flag_and_contract_to_evidence():
    class EmptyAnalyzer:
        def analyze(self, _observation, _state):
            return AnalysisResult("captured local response", AnalysisOutcome.PROGRESS)

    observation = Observation(
        step_id=1,
        objective="inspect a captured local response",
        proposal=ActionProposal(
            "inspect response",
            "use captured evidence",
            [ToolCall("http-1", "http_request", {})],
        ),
        tool_results=[
            ToolResult(
                "http-1",
                "http_request",
                True,
                artifact_refs=["artifact-response"],
                metadata={
                    "web_observation": {
                        "request_id": "request-001",
                        "response_body_sha256": "a" * 64,
                        "response_artifact_path": "workspace://output/web/response-001.json",
                        "flag_candidates": ["moectf{captured-answer}"],
                        "client_request_contracts": [{
                            "method": "POST",
                            "path": "/test_talent",
                            "query": [["level", "B"]],
                            "json_body": [["manifestation", "none"]],
                        }],
                    }
                },
            )
        ],
    )

    result = WebIntelligenceAnalyzer(EmptyAnalyzer()).analyze(
        observation,
        RunState(ChallengeSpec("contract-evidence", "Local", "local only", "web")),
    )

    assert [item.value for item in result.flag_candidates] == ["moectf{captured-answer}"]
    assert any(
        item.payload.get("category") == "client_request_contract"
        for item in result.knowledge_updates
    )
    assert "POST; endpoint=/test_talent?level=B" in result.recommendations
    assert "workspace://output/web/response-001.json" in result.recommendations


def test_web_surface_planner_context_is_bounded_and_injected():
    surface = WebAttackSurface(
        endpoints=[
            EndpointFinding(f"/route-{index}", parameters=[f"p{index}"])
            for index in range(5)
        ],
        parameters=[f"p{index}" for index in range(5)],
        technologies=["Flask", "SQLite", "Werkzeug"],
    )
    context = WebAttackSurfaceContextBuilder(
        endpoint_limit=2,
        parameter_limit=2,
        technology_limit=2,
    ).build(surface)
    captured: dict[str, str] = {}

    def requester(_system_prompt: str, user_prompt: str):
        captured["prompt"] = user_prompt
        return {
            "objective": "inspect captured local evidence",
            "reasoning_summary": "use one registered passive tool",
            "actions": [{"tool_name": "web_intelligence", "arguments": {}}],
        }

    challenge = ChallengeSpec("r8-context", "Local Web", "route map", "web")
    JsonPlanner(
        requester,
        web_attack_surface_context_provider=lambda _challenge, _state: context,
    ).plan(challenge, RunState(challenge), [])

    assert len(context["endpoints"]) == 2
    assert len(context["parameters"]) == 2
    assert len(context["technologies"]) == 2
    assert "Endpoint and technology entries are observations" in captured["prompt"]
    assert "{web_attack_surface_context}" not in captured["prompt"]


def test_web_intelligence_tool_registers_all_four_artifacts(tmp_path):
    workspace = WorkspaceManager(tmp_path / "workspace").create("r8-tool")
    directory = workspace.output_dir / "web"
    directory.mkdir(parents=True, exist_ok=True)
    response = _response(body="<a href='/admin'>Admin</a>")
    request = _request("request-001", "http://127.0.0.1:8000/")
    session = SessionArtifact("SessionArtifact", "request-001")
    for name, payload in (
        ("response-001.json", response.to_dict()),
        ("request-001.json", request.to_dict()),
        ("session-001.json", session.to_dict()),
    ):
        (directory / name).write_text(json.dumps(payload), encoding="utf-8")
    context = ExecutionContext(
        run_id="r8-tool-run",
        challenge_id="r8-tool",
        step_id=1,
        workspace_root=workspace.root,
        input_dir=workspace.input_dir,
        work_dir=workspace.work_dir,
        output_dir=workspace.output_dir,
        logs_dir=workspace.logs_dir,
        objective="analyze local Web artifacts",
        reasoning_summary="passive analysis only",
    )
    registry = ToolRegistry()
    registry.register(WebIntelligenceTool())
    runtime = ToolRuntime(
        registry,
        PolicyEngine(),
        ApprovalManager(),
        approval_resolver=lambda _request: True,
    )
    result = runtime.execute(
        ActionProposal(
            "analyze local Web artifacts",
            "passive analysis only",
            [
                ToolCall(
                    "analysis",
                    "web_intelligence",
                    {
                        "response_paths": ["output/web/response-001.json"],
                        "request_paths": ["output/web/request-001.json"],
                        "session_paths": ["output/web/session-001.json"],
                    },
                )
            ],
        ),
        context,
        ArtifactStore(workspace),
    )[0]

    assert result.success is True
    assert result.policy_decision["decision"] == "REQUIRE_APPROVAL"
    assert len(result.artifact_refs) == 4
    assert {
        "html-analysis.json",
        "endpoint-map.json",
        "technology.json",
        "response-diff.json",
    } == {path.name for path in directory.glob("*.json") if "-001" not in path.name}


def test_web_state_checkpoint_restore_and_cli_views(tmp_path):
    challenge = ChallengeSpec("r8-checkpoint", "Local Web", "local only", "web")
    manager = build_default_runtime_manager()
    state = manager.initialize("web", challenge)
    assert isinstance(state, WebRuntimeState)
    state.web_intelligence = WebIntelligenceManager().analyze(
        [
            _response(
                body='<meta name="generator" content="Flask">'
                '<a href="/admin">Admin</a>'
            )
        ]
    )
    checkpoint = tmp_path / "checkpoint"
    IntelligenceCheckpoint(checkpoint).save(
        RunState(challenge),
        IntelligenceStore.create(challenge.challenge_id),
        [],
        state,
    )

    restored = IntelligenceCheckpoint(checkpoint).load().domain_runtime_state
    assert isinstance(restored, WebRuntimeState)
    assert restored.web_intelligence.attack_surface.endpoints[0].path == "/admin"
    assert "Flask" in restored.web_intelligence.attack_surface.technologies
    surface = runner.invoke(app, ["web", "surface", "--checkpoint", str(checkpoint)])
    endpoints = runner.invoke(app, ["web", "endpoints", "--checkpoint", str(checkpoint)])
    technologies = runner.invoke(
        app,
        ["web", "technologies", "--checkpoint", str(checkpoint)],
    )
    assert surface.exit_code == endpoints.exit_code == technologies.exit_code == 0
    assert "Web Attack Surface" in surface.stdout
    assert "/admin" in endpoints.stdout
    assert "Flask" in technologies.stdout
