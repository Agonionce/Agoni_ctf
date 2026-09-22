"""Deterministic R14 local MCP Foundation end-to-end demonstration."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.intelligence.store import IntelligenceStore
from agent.mcp.adapter import MCPToolAdapterRegistry
from agent.mcp.client import MCPClientManager
from agent.mcp.registry import MCPServerRegistry
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    RunBudget,
    ToolCall,
)
from agent.runtime.runtime import AgentRuntime
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime, ToolRuntimeExecutor
from agent.workspace.manager import WorkspaceManager


def run_demo(root: str | Path) -> str:
    fixture = Path(__file__).with_name("r14_mcp_fixture_server.py")
    config = {
        "servers": [{
            "id": "local_fixture",
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(fixture)],
            "enabled": True,
            "tool_capabilities": {
                "read_fake_record": {
                    "read_only": True,
                    "state_changing": False,
                    "network": False,
                    "filesystem": False,
                    "execution": False,
                    "external_application": False,
                },
            },
        }],
    }
    servers = MCPServerRegistry.from_config(config)
    clients = MCPClientManager(servers)
    tools = ToolRegistry()
    MCPToolAdapterRegistry(clients).register_discovered(tools)
    challenge = ChallengeSpec("r14-mcp-demo", "Local MCP demo", "fixture only", "misc")

    class Planner:
        def plan(self, _challenge, _state, _schemas):
            return ActionProposal(
                "read one local MCP fixture record",
                "exercise the normal ToolRuntime boundary",
                [ToolCall("read-record", "mcp__local_fixture__read_fake_record", {"record_id": "alpha"})],
            )

    class Analyzer:
        def analyze(self, observation, _state):
            assert observation.tool_results[0].metadata["mcp"]["server"] == "local_fixture"
            return AnalysisResult("MCP result entered the ordinary Observation path", AnalysisOutcome.PROGRESS)

    executor = ToolRuntimeExecutor(
        ToolRuntime(tools, PolicyEngine(), ApprovalManager()),
        WorkspaceManager(root),
    )
    runtime = AgentRuntime(
        challenge, Planner(), executor, Analyzer(),
        budget=RunBudget(max_steps=1),
        intelligence_store=IntelligenceStore.create(challenge.challenge_id),
    )
    state = runtime.run()
    assert len(state.steps) == 1
    assert state.steps[0].tool_results[0].success is True
    artifacts = executor.artifacts_for_current_workspace()
    assert len(artifacts) == 1 and artifacts[0].artifact_type == "mcp_result"
    return "LOCAL_MCP_FOUNDATION_OK"


if __name__ == "__main__":
    with TemporaryDirectory(prefix="agonionce-r14-mcp-") as directory:
        print(run_demo(Path(directory) / "workspace"))
