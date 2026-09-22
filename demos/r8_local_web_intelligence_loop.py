"""R8 authorized loopback Web intelligence and experiment demo."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Flask, make_response, request
from werkzeug.serving import WSGIRequestHandler, make_server

from agent.domains.manager import build_default_runtime_manager
from agent.domains.web.analyzer import WebResponseAnalyzer
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.models import ExperimentStatus
from agent.intelligence.models import ArtifactReference, HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.intelligence.updater import KnowledgeUpdater
from agent.policy.approval import ApprovalManager, ApprovalStatus
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    Observation,
    RunState,
    ToolCall,
)
from agent.tools.http_request import HTTPRequestTool
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime, ToolRuntimeExecutor
from agent.tools.web_intelligence import WebIntelligenceTool
from agent.workspace.manager import WorkspaceManager


DEMO_TOKEN = "LOCAL_WEB_INTELLIGENCE_LOOP_OK"


def build_fake_local_app() -> Flask:
    """Create the deterministic localhost-only Flask challenge."""

    app = Flask("agonionce-r8-local-demo")

    def html_response(body: str, status: int = 200):
        response = make_response(body, status)
        response.headers["X-Powered-By"] = "Flask"
        response.set_cookie("session", "local-demo", httponly=True)
        return response

    @app.get("/")
    def index():
        return html_response(
            """<!doctype html>
<html><head><title>Local Research App</title>
<meta name="generator" content="Flask"></head><body>
<!-- local demo routes only -->
<form action="/login" method="post">
  <input name="username"><input name="password" type="password">
</form>
<a href="/article?id=">Article</a><a href="/admin">Admin</a>
<script src="/static/app.js"></script>
</body></html>"""
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        return html_response("<html><title>Login</title>Local login</html>")

    @app.get("/article")
    def article():
        article_id = request.args.get("id", "")
        if article_id == "2":
            return html_response(
                    "<html><title>Article Error</title>"
                    "<body>SQLite database error: article unavailable</body></html>",
            )
        return html_response(
            f"<html><title>Article {article_id}</title>"
            f"<body>Local article {article_id}</body></html>"
        )

    @app.get("/admin")
    def admin():
        return html_response("<html><title>Admin</title>Forbidden</html>", 403)

    return app


class _QuietRequestHandler(WSGIRequestHandler):
    def log(self, _log_type: str, _message: str, *args: object) -> None:
        del args
        return


@contextmanager
def fake_local_web_challenge():
    server = make_server(
        "127.0.0.1",
        0,
        build_fake_local_app(),
        threaded=True,
        request_handler=_QuietRequestHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _execute(
    executor: ToolRuntimeExecutor,
    run_state: RunState,
    step_id: int,
    objective: str,
    call: ToolCall,
) -> Observation:
    proposal = ActionProposal(
        objective=objective,
        reasoning_summary="authorized localhost R8 demo action",
        actions=[call],
    )
    executor.prepare(run_state, step_id, proposal)
    return Observation(
        step_id=step_id,
        objective=objective,
        proposal=proposal,
        tool_results=executor.execute(proposal),
        state_view={"scope": "authorized localhost demo"},
    )


def _analysis_call(call_id: str) -> ToolCall:
    return ToolCall(
        call_id,
        "web_intelligence",
        {
            "response_paths": [
                "output/web/response-001.json",
                "output/web/response-002.json",
                "output/web/response-003.json",
            ],
            "request_paths": [
                "output/web/request-001.json",
                "output/web/request-002.json",
                "output/web/request-003.json",
            ],
            "session_paths": [
                "output/web/session-001.json",
                "output/web/session-002.json",
                "output/web/session-003.json",
            ],
        },
    )


def run_demo(workspace_root: str | Path) -> str:
    with fake_local_web_challenge() as base_url:
        challenge = ChallengeSpec(
            challenge_id="r8-fake-local-web",
            title="Fake local Web intelligence challenge",
            description="Map and compare a deterministic localhost application.",
            category="web",
            authorization_scope="authorized_local_demo",
            metadata={"base_url": base_url, "authorized_targets": [base_url]},
        )
        run_state = RunState(challenge, run_id="r8-local-web-run")
        domain_manager = build_default_runtime_manager()
        web_state = domain_manager.initialize("web", challenge)
        assert isinstance(web_state, WebRuntimeState)
        registry = ToolRegistry()
        registry.register(HTTPRequestTool())
        registry.register(WebIntelligenceTool())
        approvals = ApprovalManager()
        executor = ToolRuntimeExecutor(
            ToolRuntime(
                registry,
                PolicyEngine(),
                approvals,
                approval_resolver=lambda _request: True,
            ),
            WorkspaceManager(workspace_root),
        )
        intelligence = IntelligenceStore.create(challenge.challenge_id)

        observations = [
            _execute(
                executor,
                run_state,
                1,
                "capture the local application root",
                ToolCall(
                    "root",
                    "http_request",
                    {"method": "GET", "url": f"{base_url}/", "timeout": 2},
                ),
            ),
            _execute(
                executor,
                run_state,
                2,
                "capture the first local article behavior",
                ToolCall(
                    "article-1",
                    "http_request",
                    {
                        "method": "GET",
                        "url": f"{base_url}/article",
                        "params": {"id": "1"},
                        "timeout": 2,
                    },
                ),
            ),
            _execute(
                executor,
                run_state,
                3,
                "capture a contrasting local article behavior",
                ToolCall(
                    "article-2",
                    "http_request",
                    {
                        "method": "GET",
                        "url": f"{base_url}/article",
                        "params": {"id": "2"},
                        "timeout": 2,
                    },
                ),
            ),
        ]
        for observation in observations:
            if not observation.tool_results[0].success:
                raise RuntimeError(observation.tool_results[0].error)
            domain_manager.route_observation(
                {"summary": observation.objective, "observation": observation}
            )

        analysis_observation = _execute(
            executor,
            run_state,
            4,
            "build passive Web intelligence from captured artifacts",
            _analysis_call("web-analysis"),
        )
        result = analysis_observation.tool_results[0]
        if not result.success:
            raise RuntimeError(result.error)
        suggestions = WebResponseAnalyzer().suggestions(analysis_observation)
        KnowledgeUpdater(intelligence).apply(
            AnalysisResult(
                summary="passive Web attack surface and behavior analyzed",
                outcome=AnalysisOutcome.PROGRESS,
                knowledge_updates=suggestions,
            ),
            analysis_observation,
        )
        domain_manager.route_observation(
            {
                "summary": "R8 Web intelligence captured",
                "observation": analysis_observation,
            },
            phase_complete=True,
        )

        if not intelligence.state.hypotheses:
            raise RuntimeError("Web analyzer did not propose a hypothesis")
        hypothesis = intelligence.state.hypotheses[0]
        experiment_manager = ExperimentManager(intelligence)
        experiment = experiment_manager.create_experiment(
            hypothesis.id,
            "re-run the passive comparison and preserve its evidence",
            {
                "tool_name": "web_intelligence",
                "arguments": _analysis_call("unused").arguments,
            },
            "the captured article responses retain a database-related difference",
        )
        experiment_manager.start_experiment(experiment.experiment_id)
        domain_manager.next_phase("EXPLOITATION")
        experiment_observation = _execute(
            executor,
            run_state,
            5,
            experiment.goal,
            _analysis_call("web-experiment"),
        )
        experiment_result = experiment_observation.tool_results[0]
        if not experiment_result.success:
            raise RuntimeError(experiment_result.error)
        evidence = experiment_manager.record_evidence(
            experiment.experiment_id,
            source="R8 passive response comparison",
            observation=(
                "captured responses retained a different title, length, and "
                "SQLite error signal"
            ),
            artifact_refs=[
                ArtifactReference(item, "evidence_for")
                for item in experiment_result.artifact_refs
            ],
        )
        experiment_manager.record_result(
            experiment.experiment_id,
            "passive comparison reproduced the observed behavior",
        )
        experiment_manager.close_experiment(
            experiment.experiment_id,
            ExperimentStatus.SUCCESS,
        )
        experiment_manager.close_hypothesis(
            hypothesis.id,
            HypothesisStatus.CONFIRMED,
            [evidence.evidence_id],
        )
        domain_manager.next_phase("VERIFY")
        candidate = FlagCandidate(
            DEMO_TOKEN,
            "local R8 demo completion marker",
            1.0,
            "the authorized local intelligence and experiment loop completed",
        )

    surface = web_state.web_intelligence.attack_surface
    paths = {item.path for item in surface.endpoints}
    if not {"/login", "/article", "/admin"}.issubset(paths):
        raise RuntimeError("expected local endpoints were not mapped")
    if "id" not in surface.parameters or "Flask" not in surface.technologies:
        raise RuntimeError("expected Web parameters or technology evidence is missing")
    if not any(
        item.title == "Possible database-related behavior"
        for item in intelligence.state.findings
    ):
        raise RuntimeError("database behavior Finding was not stored")
    if hypothesis.status is not HypothesisStatus.CONFIRMED:
        raise RuntimeError("experiment evidence did not close the hypothesis")
    if experiment.status is not ExperimentStatus.SUCCESS:
        raise RuntimeError("experiment did not complete")
    if any(
        request.status is not ApprovalStatus.APPROVED
        for request in approvals.list()
    ):
        raise RuntimeError("an approved R8 action did not retain approval evidence")
    required_artifacts = {
        "output/web/html-analysis.json",
        "output/web/endpoint-map.json",
        "output/web/technology.json",
        "output/web/response-diff.json",
    }
    artifact_paths = {
        artifact.path for artifact in executor.artifacts_for_current_workspace()
    }
    if not required_artifacts.issubset(artifact_paths):
        raise RuntimeError("R8 analysis artifacts were not registered")
    return candidate.value


if __name__ == "__main__":
    with TemporaryDirectory(prefix="agonionce-r8-") as directory:
        print(run_demo(Path(directory) / "workspace"))
