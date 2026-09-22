from __future__ import annotations

from agent.policy.engine import PolicyDecisionType, PolicyEngine
from agent.runtime.contracts import ToolCall
from agent.tools.contracts import ExecutionContext
from agent.tools.registry import build_default_registry
from agent.workspace.manager import WorkspaceManager


def _context(tmp_path) -> ExecutionContext:
    workspace = WorkspaceManager(tmp_path / "workspace").create("policy-demo")
    (workspace.work_dir / "chall").write_text("local artifact", encoding="utf-8")
    return ExecutionContext(
        run_id="run-policy",
        challenge_id="policy-demo",
        step_id=1,
        workspace_root=workspace.root,
        input_dir=workspace.input_dir,
        work_dir=workspace.work_dir,
        output_dir=workspace.output_dir,
        logs_dir=workspace.logs_dir,
        objective="inspect authorized local file",
        reasoning_summary="policy test",
    )


def test_policy_allows_low_risk_workspace_file_inspection(tmp_path):
    registry = build_default_registry()
    file_tool = registry.get("file")
    assert file_tool is not None

    decision = PolicyEngine().evaluate(
        ToolCall("file-1", "file", {"path": "chall"}),
        file_tool.metadata,
        _context(tmp_path),
    )

    assert decision.decision is PolicyDecisionType.ALLOW


def test_policy_requires_approval_for_curl_without_executing_it(tmp_path):
    registry = build_default_registry()
    bash_tool = registry.get("bash")
    assert bash_tool is not None

    decision = PolicyEngine().evaluate(
        ToolCall("bash-1", "bash", {"command": "curl target"}),
        bash_tool.metadata,
        _context(tmp_path),
    )

    assert decision.decision is PolicyDecisionType.REQUIRE_APPROVAL


def test_policy_denies_rm_root_without_executing_it(tmp_path):
    registry = build_default_registry()
    bash_tool = registry.get("bash")
    assert bash_tool is not None

    decision = PolicyEngine().evaluate(
        ToolCall("bash-2", "bash", {"command": "rm -rf /"}),
        bash_tool.metadata,
        _context(tmp_path),
    )

    assert decision.decision is PolicyDecisionType.DENY


def test_filesystem_policy_denies_paths_outside_workspace(tmp_path):
    registry = build_default_registry()
    file_tool = registry.get("file")
    assert file_tool is not None

    decision = PolicyEngine().evaluate(
        ToolCall("file-2", "file", {"path": "/"}),
        file_tool.metadata,
        _context(tmp_path),
    )

    assert decision.decision is PolicyDecisionType.DENY
