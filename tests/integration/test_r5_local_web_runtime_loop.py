"""R5 local Fake Web Server demo; no public or unauthorized target."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent.domains.integration import DomainRuntimeAnalyzer
from agent.domains.manager import build_default_runtime_manager
from agent.domains.web.analyzer import WebResponseAnalyzer
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.store import IntelligenceStore
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    RunBudget,
    RunStatus,
    ToolCall,
)
from agent.runtime.runtime import AgentRuntime
from agent.tools.http_request import HTTPRequestTool
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime, ToolRuntimeExecutor
from agent.workspace.manager import WorkspaceManager


DEMO_TOKEN = "LOCAL_WEB_RUNTIME_LOOP_OK"


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "AgonionceLocalDemo/1.0"
    sys_version = ""

    def do_GET(self):
        body = f"endpoint=/; {DEMO_TOKEN}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Powered-By", "FakeWebRuntime")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


@contextmanager
def local_demo_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class DemoPlanner:
    def __init__(self, url: str) -> None:
        self.url = url

    def plan(self, _challenge, _state, _tool_schemas):
        return ActionProposal(
            "observe the authorized local Web challenge root",
            "perform one read-only loopback GET",
            [
                ToolCall(
                    "local-get",
                    "http_request",
                    {"method": "GET", "url": self.url, "timeout": 2},
                )
            ],
        )


class DemoAnalyzer:
    def __init__(self) -> None:
        self.extractor = WebResponseAnalyzer()

    def analyze(self, observation, _state):
        web = observation.tool_results[0].metadata["web_observation"]
        body = web["response_body_preview"]
        candidates = []
        if DEMO_TOKEN in body:
            candidates.append(
                FlagCandidate(
                    DEMO_TOKEN,
                    "local Fake Web response",
                    1.0,
                    "the loopback response contained the local demo token",
                )
            )
        return AnalysisResult(
            summary="local HTTP response captured and classified",
            outcome=AnalysisOutcome.PROGRESS,
            flag_candidates=candidates,
            confidence=1.0,
            knowledge_updates=self.extractor.suggestions(observation),
        )


def run_demo(workspace_root) -> str:
    with local_demo_server() as url:
        challenge = ChallengeSpec(
            "r5-local-web-demo",
            "Fake local Web challenge",
            "Authorized loopback endpoint observation",
            category="web",
            authorization_scope="authorized_local_demo",
            metadata={"base_url": url},
        )
        manager = build_default_runtime_manager()
        web_state = manager.initialize("web", challenge)
        assert isinstance(web_state, WebRuntimeState)
        registry = ToolRegistry()
        registry.register(HTTPRequestTool())
        approvals = ApprovalManager()
        executor = ToolRuntimeExecutor(
            ToolRuntime(registry, PolicyEngine(), approvals),
            WorkspaceManager(workspace_root),
        )
        intelligence = IntelligenceStore.create(challenge.challenge_id)
        runtime = AgentRuntime(
            challenge=challenge,
            planner=DemoPlanner(url),
            executor=executor,
            analyzer=DomainRuntimeAnalyzer(DemoAnalyzer(), manager),
            budget=RunBudget(max_steps=2, max_llm_calls=5),
            tool_schemas=registry.schemas(),
            intelligence_store=intelligence,
            flag_confirmer=lambda candidate: candidate.value == DEMO_TOKEN,
        )

        state = runtime.run()

    facts = [fact.content for fact in intelligence.state.facts]
    assert state.status is RunStatus.SOLVED
    assert "endpoint=/" in facts
    assert web_state.endpoints == ["/"]
    assert web_state.technologies
    assert web_state.phase == "RECON"
    assert manager.next_phase().phase == "ANALYSIS"
    assert approvals.list() == []
    assert [artifact.artifact_type for artifact in executor.artifacts_for_current_workspace()] == [
        "web_request",
        "web_response",
        "web_session",
    ]
    return state.termination.flag_candidate.value


def test_local_web_runtime_loop(tmp_path):
    assert run_demo(tmp_path / "workspace") == DEMO_TOKEN


if __name__ == "__main__":
    from tempfile import TemporaryDirectory
    from pathlib import Path

    with TemporaryDirectory(prefix="agonionce-r5-") as directory:
        print(run_demo(Path(directory) / "workspace"))
