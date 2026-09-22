from __future__ import annotations

import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from typer.testing import CliRunner

from agent.domains.manager import build_default_runtime_manager
from agent.domains.web.research.context import WebResearchContextBuilder
from agent.domains.web.research.evidence import WebEvidenceFactory
from agent.domains.web.research.experiments import WebExperimentCatalog
from agent.domains.web.research.manager import WebResearchManager
from agent.domains.web.research.models import (
    AuthenticationStatus,
    WebEvidenceType,
    WebExperimentType,
    WebFlagVerificationStatus,
    WebSessionStatus,
)
from agent.domains.web.research.session import WebSessionManager
from agent.domains.web.state import WebRuntimeState
from agent.artifacts.store import ArtifactStore
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.experiment.models import Experiment
from agent.intelligence.experiment.runtime.evaluator import (
    EvidenceFactory,
    ExperimentEvaluator,
)
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluationStatus,
)
from agent.intelligence.store import IntelligenceStore
from agent.policy.engine import (
    PolicyEngine,
    PolicyDecisionType,
    TargetPolicy,
    WebRequestPolicy,
)
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    Observation,
    RunState,
    ToolCall,
    ToolResult,
)
from agent.tools.contracts import ExecutionContext
from agent.tools.http_request import HTTPRequestTool
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime
from agent.policy.approval import ApprovalManager
from agent.workspace.manager import WorkspaceManager
from cli.app import app


runner = CliRunner()


class _SessionHandler(BaseHTTPRequestHandler):
    received_cookie = ""

    def do_GET(self):
        type(self).received_cookie = self.headers.get("Cookie", "")
        body = b'<input name="csrf_token" value="local-csrf">'
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Set-Cookie", "session=local-session; HttpOnly")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


@contextmanager
def _session_server():
    _SessionHandler.received_cookie = ""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SessionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _challenge() -> ChallengeSpec:
    return ChallengeSpec(
        "r11-local",
        "R11 local Web",
        "Authorized fake local Web research",
        category="web",
        authorization_scope="authorized_local_demo",
        metadata={"base_url": "http://127.0.0.1:8080"},
    )


def _state() -> WebRuntimeState:
    manager = build_default_runtime_manager()
    state = manager.initialize("web", _challenge())
    assert isinstance(state, WebRuntimeState)
    return state


def _context(tmp_path: Path) -> ExecutionContext:
    for name in ("input", "work", "output", "logs"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    return ExecutionContext(
        run_id="run-r11",
        challenge_id="r11-local",
        step_id=1,
        workspace_root=tmp_path,
        input_dir=tmp_path / "input",
        work_dir=tmp_path / "work",
        output_dir=tmp_path / "output",
        logs_dir=tmp_path / "logs",
        objective="observe local state",
        reasoning_summary="bounded local evidence",
        authorized_targets=("http://127.0.0.1:8080",),
    )


def test_web_application_model_tracks_entities_and_relationships():
    state = _state()
    model = state.application_model
    model.record_endpoint(
        "/login",
        method="POST",
        parameters=["username", "csrf_token"],
        status_code=200,
        artifact_refs=["artifact-login"],
    )
    model.record_technology("Flask", evidence="response header", source="request-001")

    restored = WebRuntimeState.from_dict(state.to_dict())

    assert restored.application_model.endpoints[0].path == "/login"
    assert {item.name for item in restored.application_model.parameters} == {
        "username",
        "csrf_token",
    }
    assert any(item.relation == "ACCEPTS_PARAMETER"
               for item in restored.application_model.relationships)
    assert restored.application_model.technologies[0].name == "Flask"


def test_session_lifecycle_is_origin_bound_and_safe_view_masks_values():
    state = _state()
    manager = WebSessionManager(state.sessions)
    session = manager.create("http://127.0.0.1:8080", session_id="research")
    manager.set_headers("research", {"Accept": "text/html"})
    manager.update_response(
        "research",
        url="http://127.0.0.1:8080/login",
        method="POST",
        status_code=200,
        headers=[("X-CSRF-Token", "private-csrf")],
        response_cookies={"session": "private-cookie"},
        body='<input type="hidden" name="csrf_token" value="private-form-token">',
    )

    assert session.status is WebSessionStatus.AUTHENTICATED
    assert session.authentication_status is AuthenticationStatus.AUTHENTICATED
    safe = session.safe_dict()
    assert safe["cookie_names"] == ["session"]
    assert "private-cookie" not in str(safe)
    assert "private-csrf" not in str(safe)
    try:
        manager.request_state("research", "http://127.0.0.1:9090/")
    except ValueError as error:
        assert "cannot cross" in str(error)
    else:
        raise AssertionError("cross-origin session reuse must be rejected")


def test_session_id_forces_stateful_http_approval(tmp_path):
    call = ToolCall(
        "session-get",
        "http_request",
        {
            "method": "GET",
            "url": "http://127.0.0.1:8080/account",
            "session_id": "research",
        },
    )
    decision = WebRequestPolicy(TargetPolicy()).evaluate(call, _context(tmp_path))
    assert decision.decision is PolicyDecisionType.REQUIRE_APPROVAL


def test_http_tool_reuses_runtime_bound_session_through_controlled_path(tmp_path):
    state = _state()
    sessions = WebSessionManager(state.sessions)
    tool = HTTPRequestTool(sessions)
    registry = ToolRegistry()
    registry.register(tool)
    runtime = ToolRuntime(
        registry,
        PolicyEngine(),
        ApprovalManager(),
        approval_resolver=lambda _request: True,
    )
    workspace = WorkspaceManager(tmp_path / "workspace").create("r11-session")
    store = ArtifactStore(workspace)
    with _session_server() as base_url:
        sessions.create(base_url, session_id="research")
        context = ExecutionContext(
            run_id="run-r11-session",
            challenge_id="r11-session",
            step_id=1,
            workspace_root=workspace.root,
            input_dir=workspace.input_dir,
            work_dir=workspace.work_dir,
            output_dir=workspace.output_dir,
            logs_dir=workspace.logs_dir,
            objective="continue an authorized local session",
            reasoning_summary="verify controlled session continuity",
            authorized_targets=(base_url,),
        )
        proposal = ActionProposal(
            "continue an authorized local session",
            "verify controlled session continuity",
            [ToolCall("session-1", "http_request", {
                "method": "GET",
                "url": f"{base_url}/account",
                "session_id": "research",
            })],
        )
        first = runtime.execute(proposal, context, store)[0]
        second = runtime.execute(proposal, context, store)[0]

    assert first.success and second.success
    assert first.policy_decision["decision"] == "REQUIRE_APPROVAL"
    assert _SessionHandler.received_cookie == "session=local-session"
    assert sessions.get("research").cookies["session"] == "local-session"
    assert "local-session" not in str(second.metadata["web_observation"])


def test_web_experiment_catalog_defines_bounded_evidence_contracts():
    state = _state()
    state.application_model.record_endpoint("/article", parameters=["id"])
    catalog = WebExperimentCatalog()
    proposals = catalog.proposals(
        state.application_model,
        state.sessions,
        "ANALYSIS",
    )

    assert set(catalog.DEFINITIONS) == set(WebExperimentType)
    assert any(item["experiment_type"] == WebExperimentType.PARAMETER_BEHAVIOR.value
               for item in proposals)
    assert all(item["evidence_type"] in {value.value for value in WebEvidenceType}
               for item in proposals)
    assert all("tool" not in item and "payload" not in item for item in proposals)


def test_structured_web_evidence_has_provenance_and_reaches_evaluator():
    result = ToolResult(
        "compare",
        "fake_web_observe",
        True,
        stdout="captured local comparison",
        artifact_refs=["artifact-response"],
        metadata={
            "web_evidence": [{
                "evidence_type": "RESPONSE_BEHAVIOR",
                "observation": "response behavior changed",
                "endpoint": "/article",
                "parameter": "id",
            }]
        },
    )
    web = WebEvidenceFactory().create_many(
        result,
        experiment_id="exp-web",
        observation_id="obs-web",
    )
    generic = EvidenceFactory().create(
        result,
        experiment_id="exp-web",
        hypothesis_id="hyp-web",
        observation_id="obs-web",
    )
    experiment = Experiment(
        experiment_id="exp-web",
        hypothesis_id="hyp-web",
        goal="compare local responses",
        action={"tool_name": "fake_web_observe", "arguments": {}},
        expected_result="response behavior changed",
    )
    evaluation = ExperimentEvaluator().evaluate(experiment, [generic], [result])

    assert web[0].artifact_refs == ["artifact-response"]
    assert web[0].experiment_id == "exp-web"
    assert evaluation.status is ExperimentEvaluationStatus.SUPPORTED


def test_flag_candidate_requires_evidence_then_explicit_verification():
    state = _state()
    observation = Observation(
        step_id=1,
        objective="inspect captured local response",
        proposal=ActionProposal(
            "inspect captured local response",
            "bounded local observation",
            [ToolCall("observe", "fake_web_observe", {})],
        ),
        tool_results=[ToolResult(
            "observe",
            "fake_web_observe",
            True,
            artifact_refs=["artifact-local-response"],
        )],
    )
    candidate = FlagCandidate(
        "LOCAL_R11_CANDIDATE",
        "fake local response",
        0.9,
        "captured response contained a candidate marker",
    )
    manager = WebResearchManager(state)
    manager.observe(
        observation,
        AnalysisResult(
            "candidate observed",
            AnalysisOutcome.PROGRESS,
            flag_candidates=[candidate],
        ),
    )

    assert state.flag_candidates[0].verification_status is WebFlagVerificationStatus.EVIDENCE_BOUND
    assert "LOCAL_R11_CANDIDATE" not in str(state.flag_candidates[0].safe_dict())
    manager.verify_flag(candidate, True)
    assert state.flag_candidates[0].verification_status is WebFlagVerificationStatus.VERIFIED


def test_web_research_checkpoint_and_experience_context_recover(tmp_path):
    state = _state()
    sessions = WebSessionManager(state.sessions)
    sessions.create("http://127.0.0.1:8080", session_id="default")
    state.application_model.record_endpoint("/article", parameters=["id"])
    result = ToolResult(
        "secret-observation",
        "fake_web_observe",
        True,
        artifact_refs=["artifact-secret-observation"],
        metadata={"web_evidence": [{
            "evidence_type": "RESPONSE_BEHAVIOR",
            "observation": "token=private-value response behavior changed",
        }]},
    )
    state.web_evidence.extend(WebEvidenceFactory().create_many(result))
    context = WebResearchContextBuilder(item_limit=2).build(
        state,
        intelligence={"facts": 1},
        relevant_experience={
            "relevant_experience": [{
                "id": "experience-web-1",
                "domain": "web",
                "category": "response_comparison",
                "strategy": "establish a baseline first",
            }]
        },
    )
    checkpoint = IntelligenceCheckpoint(tmp_path / "checkpoint")
    checkpoint.save(
        RunState(_challenge(), run_id="run-r11-checkpoint"),
        IntelligenceStore.create("r11-local"),
        domain_runtime_state=state,
    )
    restored = checkpoint.load().domain_runtime_state

    assert context["relevant_experience"][0]["id"] == "experience-web-1"
    assert "private-value" not in str(context)
    assert "private-value" not in str(state.safe_dict())
    assert context["sessions"][0]["session_id"] == "default"
    assert isinstance(restored, WebRuntimeState)
    assert restored.application_model.parameters[0].name == "id"
    assert restored.sessions[0].session_id == "default"


def test_web_research_cli_commands_read_checkpoint(tmp_path):
    state = _state()
    WebSessionManager(state.sessions).create(
        "http://127.0.0.1:8080",
        session_id="default",
    )
    state.application_model.record_endpoint("/article", parameters=["id"])
    checkpoint = IntelligenceCheckpoint(tmp_path / "checkpoint")
    checkpoint.save(
        RunState(_challenge(), run_id="run-r11-cli"),
        IntelligenceStore.create("r11-local"),
        domain_runtime_state=state,
    )

    for command in ("model", "sessions", "experiments", "findings"):
        result = runner.invoke(
            app,
            ["web", command, "--checkpoint", str(checkpoint.directory)],
        )
        assert result.exit_code == 0, result.output
