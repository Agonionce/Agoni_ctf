from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent.artifacts.store import ArtifactStore
from agent.intelligence.checkpoint import IntelligenceCheckpoint, RuntimeStepCheckpoint
from agent.intelligence.store import IntelligenceStore
from agent.mcp.adapter import MCPToolAdapter, MCPToolAdapterRegistry
from agent.mcp.client import MCPClientManager, MCPError
from agent.mcp.models import MCPCapabilityProfile, MCPToolDescriptor
from agent.mcp.registry import MCPServerRegistry
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    RunBudget,
    RunStatus,
    ToolCall,
)
from agent.runtime.runtime import AgentRuntime
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime, ToolRuntimeExecutor
from agent.workspace.manager import WorkspaceManager
from cli.app import app


runner = CliRunner()
FIXTURE_SERVER = Path(__file__).resolve().parents[2] / "demos" / "r14_mcp_fixture_server.py"


def _mcp_config(*, timeout: float = 2.0) -> dict:
    return {
        "servers": [{
            "id": "local_fixture",
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(FIXTURE_SERVER)],
            "enabled": True,
            "timeout_seconds": timeout,
            "tool_capabilities": {
                name: {
                    "read_only": True,
                    "state_changing": False,
                    "network": False,
                    "filesystem": False,
                    "execution": False,
                    "external_application": False,
                }
                for name in ("echo", "list_fixture", "read_fake_record", "calculate", "slow_echo")
            },
        }],
    }


def _adapter_registry() -> tuple[MCPClientManager, ToolRegistry]:
    manager = MCPClientManager(MCPServerRegistry.from_config(_mcp_config()))
    tools = ToolRegistry()
    MCPToolAdapterRegistry(manager).register_discovered(tools)
    return manager, tools


def test_mcp_config_is_explicit_local_and_defaults_unknown_tools_to_high_risk():
    registry = MCPServerRegistry.from_config(_mcp_config())
    server = registry.get("local_fixture")

    assert server is not None
    assert server.capability_for("echo").risk_level.value == "LOW"
    assert server.capability_for("set_fixture_note").risk_level.value == "HIGH"
    assert "command" not in server.safe_dict()
    registry.mark_error("local_fixture", "token=private-value flag{private-answer}")
    assert "private" not in str(registry.status("local_fixture").safe_dict())
    with pytest.raises(ValueError, match="capability declaration"):
        MCPServerRegistry.from_config({"servers": [{
            "id": "bad", "transport": "stdio", "command": "python",
            "tool_capabilities": {"tool": "not-an-object"},
        }]})


def test_stdio_mcp_discovery_call_error_and_timeout_are_normalized():
    registry = MCPServerRegistry.from_config(_mcp_config(timeout=0.1))
    manager = MCPClientManager(registry)

    discovered = manager.discover("local_fixture")
    assert {item.name for item in discovered} >= {"echo", "read_fake_record", "calculate"}
    call = manager.call_tool("local_fixture", "calculate", {"left": 7, "right": 11})
    assert call.result["content"][0]["text"] == '{"sum": 18}'
    with pytest.raises(MCPError, match="timed out"):
        manager.call_tool("local_fixture", "slow_echo", {"delay_ms": 500})
    assert registry.status("local_fixture").health.value == "ERROR"


def test_mcp_adapter_uses_toolruntime_policy_artifact_and_audit(tmp_path):
    _manager, tools = _adapter_registry()
    workspace = WorkspaceManager(tmp_path / "workspace").create("r14-mcp")
    runtime = ToolRuntime(tools, PolicyEngine(), ApprovalManager())
    proposal = ActionProposal(
        "read an authorized local MCP fixture record",
        "use the discovered read-only capability",
        [ToolCall("mcp-read", "mcp__local_fixture__read_fake_record", {"record_id": "alpha"})],
    )
    from agent.tools.contracts import ExecutionContext
    context = ExecutionContext(
        run_id="r14-mcp-run", challenge_id="r14-mcp", step_id=1,
        workspace_root=workspace.root, input_dir=workspace.input_dir,
        work_dir=workspace.work_dir, output_dir=workspace.output_dir,
        logs_dir=workspace.logs_dir, objective=proposal.objective,
        reasoning_summary=proposal.reasoning_summary,
    )
    result = runtime.execute(proposal, context, ArtifactStore(workspace))[0]

    assert result.success is True
    assert result.policy_decision["decision"] == "ALLOW"
    assert result.metadata["mcp"]["server"] == "local_fixture"
    assert result.metadata["mcp"]["remote_tool"] == "read_fake_record"
    assert len(result.artifact_refs) == 1
    output = next((workspace.output_dir / "mcp").glob("*.json"))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["result"]["content"][0]["text"] == '{"id": "alpha", "kind": "fixture", "value": 7}'
    assert runtime.audit_records[-1].metadata["mcp"]["server"] == "local_fixture"


def test_mcp_state_changing_tool_requires_existing_approval_path(tmp_path):
    _manager, tools = _adapter_registry()
    workspace = WorkspaceManager(tmp_path / "workspace").create("r14-mcp-approval")
    proposal = ActionProposal(
        "change only the local fixture process state",
        "verify the normal approval boundary",
        [ToolCall("mcp-write", "mcp__local_fixture__set_fixture_note", {"note": "local"})],
    )
    from agent.tools.contracts import ExecutionContext
    context = ExecutionContext(
        run_id="r14-mcp-approval-run", challenge_id="r14-mcp-approval", step_id=1,
        workspace_root=workspace.root, input_dir=workspace.input_dir,
        work_dir=workspace.work_dir, output_dir=workspace.output_dir,
        logs_dir=workspace.logs_dir, objective=proposal.objective,
        reasoning_summary=proposal.reasoning_summary,
    )
    denied = ToolRuntime(tools, PolicyEngine(), ApprovalManager()).execute(
        proposal, context, ArtifactStore(workspace)
    )[0]
    approved = ToolRuntime(
        tools, PolicyEngine(), ApprovalManager(), approval_resolver=lambda _request: True
    ).execute(proposal, context, ArtifactStore(workspace))[0]

    assert denied.success is False
    assert denied.error == "approval required and not granted"
    assert denied.policy_decision["decision"] == "REQUIRE_APPROVAL"
    assert approved.success is True
    assert approved.policy_decision["decision"] == "REQUIRE_APPROVAL"


def test_mcp_adapter_normalizes_remote_tool_error_to_artifact(tmp_path):
    manager = MCPClientManager(MCPServerRegistry.from_config(_mcp_config()))
    adapter = MCPToolAdapter(
        manager,
        MCPToolDescriptor("local_fixture", "does_not_exist", "bad remote tool", {
            "type": "object", "properties": {}, "additionalProperties": False,
        }),
        MCPCapabilityProfile(
            read_only=True, state_changing=False, external_application=False,
        ),
    )
    workspace = WorkspaceManager(tmp_path / "workspace").create("r14-mcp-error")
    from agent.tools.contracts import ExecutionContext
    context = ExecutionContext(
        run_id="r14-mcp-error-run", challenge_id="r14-mcp-error", step_id=1,
        workspace_root=workspace.root, input_dir=workspace.input_dir,
        work_dir=workspace.work_dir, output_dir=workspace.output_dir,
        logs_dir=workspace.logs_dir, objective="local error", reasoning_summary="fixture only",
    )

    result = adapter.execute({}, context)

    assert result.success is False
    assert result.error == "MCP tool reported an error"
    assert result.artifact_paths[0].is_file()


def test_mcp_tool_result_survives_runtime_checkpoint(tmp_path):
    _manager, tools = _adapter_registry()
    challenge = ChallengeSpec("r14-mcp-checkpoint", "Local MCP", "fixture only", "misc")

    class Planner:
        def plan(self, _challenge, _state, _schemas):
            return ActionProposal(
                "read an MCP fixture record",
                "one local read-only Tool call",
                [ToolCall("mcp", "mcp__local_fixture__read_fake_record", {"record_id": "beta"})],
            )

    class Analyzer:
        def analyze(self, _observation, _state):
            return AnalysisResult("MCP result observed", AnalysisOutcome.PROGRESS)

    executor = ToolRuntimeExecutor(
        ToolRuntime(tools, PolicyEngine(), ApprovalManager()),
        WorkspaceManager(tmp_path / "workspace"),
    )
    intelligence = IntelligenceStore.create(challenge.challenge_id)
    checkpoint = IntelligenceCheckpoint(tmp_path / "checkpoint")
    runtime = AgentRuntime(
        challenge, Planner(), executor, Analyzer(), budget=RunBudget(max_steps=1),
        checkpoint_handler=RuntimeStepCheckpoint(
            checkpoint, intelligence, artifacts_provider=executor.artifacts_for_current_workspace,
        ),
        intelligence_store=intelligence,
    )

    state = runtime.run()
    restored = checkpoint.load()

    assert state.status is RunStatus.BUDGET_EXHAUSTED
    result = restored.run_state.steps[0].tool_results[0]
    assert result.metadata["mcp"]["remote_tool"] == "read_fake_record"
    assert restored.artifacts[0]["artifact_type"] == "mcp_result"


def test_mcp_cli_discovers_local_tools_from_explicit_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"mcp": _mcp_config()}), encoding="utf-8")

    listing = runner.invoke(app, ["mcp", "list", "--config", str(config_path)])
    tools = runner.invoke(app, ["mcp", "tools", "local_fixture", "--config", str(config_path)])
    inspect = runner.invoke(app, ["mcp", "inspect", "local_fixture", "--config", str(config_path)])

    assert listing.exit_code == tools.exit_code == inspect.exit_code == 0
    assert "local_fixture" in listing.stdout
    assert "read_fake_record" in tools.stdout
    assert "schema_sha256" not in inspect.stdout
    assert "agonionce-local-fixture" in inspect.stdout
