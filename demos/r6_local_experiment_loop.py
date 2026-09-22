"""R6 fake local Web experiment loop; performs no network access."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict

from agent.domains.manager import build_default_runtime_manager
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.experiment.manager import (
    EvidenceCollector,
    ExperimentExecutor,
    ExperimentManager,
    ExperimentPlanner,
    HypothesisManager,
)
from agent.intelligence.experiment.models import ExperimentStatus
from agent.intelligence.models import HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.policy.approval import ApprovalManager, ApprovalStatus
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import (
    ActionProposal,
    ChallengeSpec,
    Observation,
    RunState,
    ToolCall,
)
from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
    ToolRiskLevel,
)
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime, ToolRuntimeExecutor
from agent.workspace.manager import WorkspaceManager


DEMO_TOKEN = "LOCAL_EXPERIMENT_LOOP_OK"
LOCAL_TARGET = "http://127.0.0.1/fake"


class FakeLocalWebTool(Tool):
    """Return deterministic fake responses without opening a socket."""

    metadata = ToolMetadata(
        name="fake_local_web",
        description="Read a deterministic in-memory localhost challenge response",
        risk_level=ToolRiskLevel.MEDIUM,
        requires_network=False,
        writes_files=False,
        execution_type="fake_local_demo",
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "id": {"type": "string"},
        },
        "required": ["url", "id"],
        "additionalProperties": False,
    }

    def execute(
        self,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        del context
        if arguments.get("url") != LOCAL_TARGET:
            return ToolExecutionOutput(False, error="fake target is outside the local demo")
        parameter = arguments.get("id")
        if parameter == "1'":
            response = "SQL syntax error near quote"
        elif parameter == "1 AND 1=2":
            response = "No rows matched"
        else:
            response = "Record 1"
        return ToolExecutionOutput(
            True,
            stdout=response,
            metadata={"target": LOCAL_TARGET, "parameter": "id"},
        )


def _execute_observation(
    executor: ToolRuntimeExecutor,
    run_state: RunState,
    proposal: ActionProposal,
    step_id: int,
) -> Observation:
    executor.prepare(run_state, step_id, proposal)
    results = executor.execute(proposal)
    return Observation(
        step_id=step_id,
        objective=proposal.objective,
        proposal=proposal,
        tool_results=results,
        state_view={"demo": "fake_local_web"},
    )


def run_demo(workspace_root: str | Path) -> str:
    """Run Observation -> Hypothesis -> Experiment -> Evidence locally."""

    challenge = ChallengeSpec(
        challenge_id="r6-fake-local-web",
        title="Fake local Web experiment challenge",
        description="An in-memory localhost parameter produces deterministic responses.",
        category="web",
        authorization_scope="authorized_local_demo",
        metadata={"base_url": LOCAL_TARGET, "authorized_targets": [LOCAL_TARGET]},
    )
    run_state = RunState(challenge)
    domain_manager = build_default_runtime_manager()
    web_state = domain_manager.initialize("web", challenge)
    assert isinstance(web_state, WebRuntimeState)

    registry = ToolRegistry()
    registry.register(FakeLocalWebTool())
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
    store = IntelligenceStore.create(challenge.challenge_id)
    manager = ExperimentManager(store)
    hypothesis_manager = HypothesisManager(manager)
    experiment_planner = ExperimentPlanner(manager)
    experiment_executor = ExperimentExecutor(manager)
    evidence_collector = EvidenceCollector(manager)

    initial_proposal = ActionProposal(
        objective="observe the fake localhost id parameter",
        reasoning_summary="collect a deterministic baseline anomaly",
        actions=[
            ToolCall(
                "fake-baseline",
                "fake_local_web",
                {"url": LOCAL_TARGET, "id": "1'"},
            )
        ],
    )
    initial_observation = _execute_observation(executor, run_state, initial_proposal, 1)
    initial_result = initial_observation.tool_results[0]
    if not initial_result.success or "SQL syntax error" not in initial_result.stdout:
        raise RuntimeError("fake SQL error observation was not produced")
    web_state.record_endpoint("/fake")
    web_state.record_parameter("id", "/fake")

    hypothesis = hypothesis_manager.create(
        statement="id parameter may be SQL injectable",
        domain="web",
        confidence=0.5,
    )
    experiment = experiment_planner.propose(
        hypothesis_id=hypothesis.id,
        goal="compare a controlled id predicate with the SQL-error observation",
        action={
            "tool_name": "fake_local_web",
            "arguments": {"url": LOCAL_TARGET, "id": "1 AND 1=2"},
        },
        expected_result="the fake response differs from the SQL-error baseline",
    )
    experiment_executor.start(experiment.experiment_id)

    experiment_proposal = ActionProposal(
        objective=experiment.goal,
        reasoning_summary="run the proposed experiment through controlled execution",
        actions=[
            ToolCall(
                "fake-experiment",
                str(experiment.action["tool_name"]),
                dict(experiment.action["arguments"]),
            )
        ],
    )
    experiment_observation = _execute_observation(
        executor,
        run_state,
        experiment_proposal,
        2,
    )
    result = experiment_observation.tool_results[0]
    if not result.success:
        raise RuntimeError(result.error or "fake experiment failed")
    evidence = evidence_collector.collect(
        experiment.experiment_id,
        source="fake_local_web ToolResult stdout",
        observation=f"response changed from SQL syntax error to: {result.stdout}",
    )
    experiment_executor.complete(
        experiment.experiment_id,
        actual_result=result.stdout,
        status=ExperimentStatus.SUCCESS,
    )
    hypothesis_manager.close(
        hypothesis.id,
        HypothesisStatus.CONFIRMED,
        [evidence.evidence_id],
    )

    if hypothesis.status is not HypothesisStatus.CONFIRMED:
        raise RuntimeError("hypothesis was not confirmed")
    if experiment.status is not ExperimentStatus.SUCCESS:
        raise RuntimeError("experiment did not close successfully")
    if web_state.parameters.get("id") != ["/fake"]:
        raise RuntimeError("Web runtime did not retain the fake parameter")
    if len(approvals.list()) != 2 or any(
        request.status is not ApprovalStatus.APPROVED for request in approvals.list()
    ):
        raise RuntimeError("fake experiment actions were not approved individually")
    return DEMO_TOKEN


if __name__ == "__main__":
    with TemporaryDirectory(prefix="agonionce-r6-") as directory:
        print(run_demo(Path(directory) / "workspace"))
