from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from agent.artifacts.store import ArtifactStore
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyDecisionType, PolicyEngine
from agent.runtime.contracts import ActionProposal, ToolCall
from agent.tools.contracts import ExecutionContext
from agent.tools.http_request import HTTPRequestTool
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime
from agent.workspace.manager import WorkspaceManager


class FakeWebHandler(BaseHTTPRequestHandler):
    server_version = "AgonionceFakeWeb/1.0"
    sys_version = ""
    post_count = 0

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/contract":
            body = (
                ("x" * 5_000)
                + "<script>fetch('/test_talent?level=B', {method: 'POST', "
                + "headers: {'Content-Type': 'application/json'}, "
                + "body: JSON.stringify({manifestation: 'none'})});</script>"
                + "moectf{long-response-answer}"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        name = parse_qs(parsed.query).get("name", ["guest"])[0]
        body = f"endpoint={parsed.path}; hello {name}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Powered-By", "FakePHP/1.0")
        self.send_header("Set-Cookie", "session=local-session; HttpOnly")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        type(self).post_count += 1
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


@contextmanager
def fake_web_server():
    FakeWebHandler.post_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _context_and_store(
    tmp_path,
    authorized_targets=("http://127.0.0.1:8080",),
):
    workspace = WorkspaceManager(tmp_path / "workspace").create("r5-http")
    context = ExecutionContext(
        run_id="run-r5-http",
        challenge_id="r5-http",
        step_id=1,
        workspace_root=workspace.root,
        input_dir=workspace.input_dir,
        work_dir=workspace.work_dir,
        output_dir=workspace.output_dir,
        logs_dir=workspace.logs_dir,
        objective="observe the authorized local fake server",
        reasoning_summary="capture one bounded local response",
        authorized_targets=authorized_targets,
    )
    return context, ArtifactStore(workspace)


def test_web_policy_allows_plain_local_get_requires_post_approval_and_denies_public(tmp_path):
    context, _store = _context_and_store(tmp_path)
    tool = HTTPRequestTool()
    policy = PolicyEngine()

    plain_get = policy.evaluate(
        ToolCall("get", "http_request", {"method": "GET", "url": "http://127.0.0.1:8080/"}),
        tool.metadata,
        context,
    )
    post = policy.evaluate(
        ToolCall(
            "post",
            "http_request",
            {"method": "POST", "url": "http://127.0.0.1:8080/login", "body": "test"},
        ),
        tool.metadata,
        context,
    )
    public = policy.evaluate(
        ToolCall("public", "http_request", {"method": "GET", "url": "https://example.com/"}),
        tool.metadata,
        context,
    )
    undeclared_local = policy.evaluate(
        ToolCall(
            "other-local",
            "http_request",
            {"method": "GET", "url": "http://127.0.0.1:9090/"},
        ),
        tool.metadata,
        context,
    )

    assert plain_get.decision is PolicyDecisionType.ALLOW
    assert post.decision is PolicyDecisionType.REQUIRE_APPROVAL
    assert public.decision is PolicyDecisionType.DENY
    assert undeclared_local.decision is PolicyDecisionType.DENY


def test_http_tool_captures_request_response_session_artifacts(tmp_path):
    registry = ToolRegistry()
    registry.register(HTTPRequestTool())
    approvals = []
    runtime = ToolRuntime(
        registry,
        PolicyEngine(),
        ApprovalManager(),
        approval_resolver=lambda request: approvals.append(request) is None,
    )
    with fake_web_server() as base_url:
        context, store = _context_and_store(tmp_path, (base_url,))
        proposal = ActionProposal(
            "observe one reflected local parameter",
            "the parameterized request has explicit test approval",
            [
                ToolCall(
                    "http-1",
                    "http_request",
                    {
                        "method": "GET",
                        "url": f"{base_url}/login",
                        "params": {"name": "agent-marker"},
                        "cookies": {"client": "local-client"},
                        "timeout": 2,
                    },
                )
            ],
        )
        result = runtime.execute(proposal, context, store)[0]

    assert result.success is True
    assert result.policy_decision["decision"] == "REQUIRE_APPROVAL"
    assert len(approvals) == 1
    assert result.artifact_refs == ["artifact-001", "artifact-002", "artifact-003"]
    assert result.metadata["web_observation"]["endpoint"] == "/login"
    assert result.metadata["web_observation"]["reflected_parameters"] == ["name"]
    assert "FakePHP/1.0" in result.metadata["web_observation"]["technologies"]
    assert [artifact.artifact_type for artifact in store.list()] == [
        "web_request",
        "web_response",
        "web_session",
    ]

    request_path = context.output_dir / "web" / "request-001.json"
    response_path = context.output_dir / "web" / "response-001.json"
    session_path = context.output_dir / "web" / "session-001.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    response = json.loads(response_path.read_text(encoding="utf-8"))
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert request["artifact_kind"] == "RequestArtifact"
    assert request["headers"]["Cookie"] == "<redacted>"
    assert response["artifact_kind"] == "ResponseArtifact"
    assert response["status_code"] == 200
    assert session["artifact_kind"] == "SessionArtifact"
    assert session["response_cookies"]["session"] == "local-session"


def test_http_tool_preserves_long_response_semantics_for_runtime(tmp_path):
    registry = ToolRegistry()
    registry.register(HTTPRequestTool())
    runtime = ToolRuntime(registry, PolicyEngine(), ApprovalManager())
    with fake_web_server() as base_url:
        context, store = _context_and_store(tmp_path, (base_url,))
        result = runtime.execute(
            ActionProposal(
                "capture a local client request contract",
                "one local GET is sufficient",
                [ToolCall("contract", "http_request", {
                    "method": "GET", "url": f"{base_url}/contract",
                })],
            ),
            context,
            store,
        )[0]

    web = result.metadata["web_observation"]
    assert web["response_body_complete"] is True
    assert len(web["response_body_preview"]) == 4096
    assert web["flag_candidates"] == ["moectf{long-response-answer}"]
    assert web["client_request_contracts"][0]["method"] == "POST"
    assert web["client_request_contracts"][0]["json_body"] == [["manifestation", "none"]]
    assert web["response_artifact_path"] == "workspace://output/web/response-001.json"


def test_http_tool_defense_in_depth_never_contacts_public_target(tmp_path):
    context, _store = _context_and_store(tmp_path)

    output = HTTPRequestTool().execute(
        {"method": "GET", "url": "https://example.com/"},
        context,
    )

    assert output.success is False
    assert "non-loopback" in (output.error or "")
    assert not list(context.output_dir.rglob("*.json"))


def test_unapproved_post_is_blocked_before_local_server_contact(tmp_path):
    registry = ToolRegistry()
    registry.register(HTTPRequestTool())
    runtime = ToolRuntime(registry, PolicyEngine(), ApprovalManager())
    with fake_web_server() as base_url:
        context, store = _context_and_store(tmp_path, (base_url,))
        proposal = ActionProposal(
            "do not execute an unapproved POST",
            "verify action-level approval",
            [
                ToolCall(
                    "post-1",
                    "http_request",
                    {"method": "POST", "url": f"{base_url}/login", "body": "test"},
                )
            ],
        )
        result = runtime.execute(proposal, context, store)[0]

    assert result.success is False
    assert result.error == "approval required and not granted"
    assert FakeWebHandler.post_count == 0
    assert store.list() == []
