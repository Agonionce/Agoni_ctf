"""R1 end-to-end demo using fake local Tools only; no shell or network backend."""

from __future__ import annotations

import json

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


class FakeWriteHelloTool(Tool):
    metadata = ToolMetadata(
        name="fake_write_hello",
        description="Create one local demo artifact.",
        risk_level=ToolRiskLevel.MEDIUM,
        requires_network=False,
        writes_files=True,
        execution_type="fake",
    )
    input_schema = {"type": "object", "properties": {}, "required": []}

    def execute(
        self,
        arguments: dict,
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        hello_path = context.work_dir / "hello.txt"
        hello_path.write_text("LOCAL_ARTIFACT_LOOP_OK", encoding="utf-8")
        return ToolExecutionOutput(
            success=True,
            stdout="hello.txt created",
            artifact_paths=[hello_path],
            artifact_type="text",
        )


class FakeReadHelloTool(Tool):
    metadata = ToolMetadata(
        name="fake_read_hello",
        description="Read the local R1 demo artifact.",
        risk_level=ToolRiskLevel.LOW,
        requires_network=False,
        writes_files=False,
        execution_type="fake",
    )
    input_schema = {"type": "object", "properties": {}, "required": []}

    def execute(
        self,
        arguments: dict,
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        return ToolExecutionOutput(
            success=True,
            stdout=(context.work_dir / "hello.txt").read_text(encoding="utf-8"),
        )


class DemoPlanner:
    def plan(self, challenge, state, tool_schemas):
        if state.current_step == 0:
            return ActionProposal(
                objective="create a local hello artifact",
                reasoning_summary="create an authorized local demonstration artifact",
                actions=[ToolCall("write-hello", "fake_write_hello", {})],
            )
        return ActionProposal(
            objective="observe the recorded hello artifact",
            reasoning_summary="read the artifact created in the previous step",
            actions=[ToolCall("read-hello", "fake_read_hello", {})],
        )


class DemoAnalyzer:
    def analyze(self, observation, state):
        if observation.step_id == 1:
            return AnalysisResult(
                summary="local artifact recorded; observation still required",
                outcome=AnalysisOutcome.PARTIAL_SUCCESS,
            )
        output = observation.tool_results[0].stdout
        return AnalysisResult(
            summary="artifact observation completed",
            outcome=AnalysisOutcome.PROGRESS,
            flag_candidates=[
                FlagCandidate(
                    "LOCAL_ARTIFACT_LOOP_OK",
                    "fake_read_hello.stdout",
                    1.0,
                    output,
                )
            ],
            confidence=1.0,
        )


def test_local_artifact_loop_routes_runtime_through_policy_approval_and_audit(tmp_path):
    registry = ToolRegistry()
    registry.register(FakeWriteHelloTool())
    registry.register(FakeReadHelloTool())
    approvals = []
    tool_runtime = ToolRuntime(
        registry=registry,
        policy_engine=PolicyEngine(),
        approval_manager=ApprovalManager(),
        approval_resolver=lambda request: approvals.append(request) is None,
    )
    executor = ToolRuntimeExecutor(
        tool_runtime=tool_runtime,
        workspace_manager=WorkspaceManager(tmp_path / "workspace"),
    )
    runtime = AgentRuntime(
        challenge=ChallengeSpec(
            challenge_id="r1-local-demo",
            title="R1 local artifact demo",
            description="authorized fake local tool demonstration",
        ),
        planner=DemoPlanner(),
        executor=executor,
        analyzer=DemoAnalyzer(),
        budget=RunBudget(max_steps=3, max_llm_calls=10),
        tool_schemas=registry.schemas(),
        flag_confirmer=lambda candidate: candidate.value == "LOCAL_ARTIFACT_LOOP_OK",
    )

    state = runtime.run()

    assert state.status is RunStatus.SOLVED
    assert state.termination is not None
    assert state.termination.flag_candidate is not None
    assert state.termination.flag_candidate.value == "LOCAL_ARTIFACT_LOOP_OK"
    assert len(approvals) == 1
    assert approvals[0].tool_name == "fake_write_hello"
    assert state.steps[0].tool_results[0].artifact_refs == ["artifact-001"]
    assert state.steps[0].tool_results[0].policy_decision == {
        "decision": "REQUIRE_APPROVAL",
        "reason": "file-writing tool requires approval",
        "risk_level": "MEDIUM",
    }
    assert [artifact.artifact_id for artifact in executor.artifacts_for_current_workspace()] == [
        "artifact-001"
    ]
    audit_path = tmp_path / "workspace" / "r1-local-demo" / "logs" / "tool-audit.jsonl"
    audit_records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [record["tool_name"] for record in audit_records] == [
        "fake_write_hello",
        "fake_read_hello",
    ]
    assert audit_records[0]["caller"] == "AgentRuntime"
    assert audit_records[1]["stdout"] == "LOCAL_ARTIFACT_LOOP_OK"
    assert (tmp_path / "workspace" / "r1-local-demo" / "work" / "hello.txt").read_text(
        encoding="utf-8"
    ) == "LOCAL_ARTIFACT_LOOP_OK"
