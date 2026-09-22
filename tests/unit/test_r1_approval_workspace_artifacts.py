from __future__ import annotations

import pytest

from agent.artifacts.store import ArtifactStore
from agent.policy.approval import ApprovalManager, ApprovalStatus
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import ActionProposal, ToolCall
from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
    ToolRiskLevel,
)
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime
from agent.tools.settings import ExecutionSettings
from agent.workspace.manager import WorkspaceManager


def test_approval_manager_tracks_pending_approved_and_rejected_requests():
    manager = ApprovalManager()
    approved = manager.request(
        tool_name="python",
        arguments={"script": "solve.py"},
        reason="run local solver",
        risk_level="MEDIUM",
    )
    rejected = manager.request(
        tool_name="bash",
        arguments={"command": "curl target"},
        reason="network request",
        risk_level="MEDIUM",
    )

    assert approved.status is ApprovalStatus.PENDING
    assert manager.approve(approved.request_id).status is ApprovalStatus.APPROVED
    assert manager.reject(rejected.request_id, "not authorized").status is ApprovalStatus.REJECTED
    with pytest.raises(ValueError, match="already decided"):
        manager.approve(approved.request_id)


def test_workspace_and_artifact_store_keep_metadata_under_one_workspace(tmp_path):
    workspace = WorkspaceManager(tmp_path / "workspace").create("artifact-demo")
    generated = workspace.work_dir / "hello.txt"
    generated.write_text("LOCAL_ARTIFACT_LOOP_OK", encoding="utf-8")

    store = ArtifactStore(workspace)
    artifact = store.register(
        generated,
        created_by="fake-write",
        source_step=1,
        artifact_type="text",
    )

    assert artifact.artifact_id == "artifact-001"
    assert artifact.path == "work/hello.txt"
    assert store.get("artifact-001") == artifact
    assert ArtifactStore(workspace).list() == [artifact]


def test_missing_execution_config_uses_manual_safe_defaults():
    assert ExecutionSettings.from_mapping(None) == ExecutionSettings(
        mode="manual",
        workspace_root="workspace",
        default_policy="safe",
    )


def test_writing_tool_is_not_executed_without_action_approval(tmp_path):
    class FakeWriteTool(Tool):
        metadata = ToolMetadata(
            name="fake_write",
            description="test-only local writer",
            risk_level=ToolRiskLevel.MEDIUM,
            requires_network=False,
            writes_files=True,
            execution_type="fake",
        )
        input_schema = {"type": "object", "properties": {}, "required": []}

        def execute(self, arguments, context):
            target = context.work_dir / "should-not-exist.txt"
            target.write_text("unexpected", encoding="utf-8")
            return ToolExecutionOutput(True, artifact_paths=[target])

    workspace = WorkspaceManager(tmp_path / "workspace").create("manual-demo")
    context = ExecutionContext(
        run_id="run-manual",
        challenge_id="manual-demo",
        step_id=1,
        workspace_root=workspace.root,
        input_dir=workspace.input_dir,
        work_dir=workspace.work_dir,
        output_dir=workspace.output_dir,
        logs_dir=workspace.logs_dir,
        objective="verify manual default",
        reasoning_summary="writes require an action-level decision",
    )
    registry = ToolRegistry()
    registry.register(FakeWriteTool())
    approvals = ApprovalManager()
    runtime = ToolRuntime(registry, PolicyEngine(), approvals)
    proposal = ActionProposal(
        "verify manual default",
        "writes require an action-level decision",
        [ToolCall("write-1", "fake_write", {})],
    )

    result = runtime.execute(proposal, context, ArtifactStore(workspace))[0]

    assert result.success is False
    assert result.error == "approval required and not granted"
    assert not (workspace.work_dir / "should-not-exist.txt").exists()
    assert approvals.list()[0].status is ApprovalStatus.REJECTED
