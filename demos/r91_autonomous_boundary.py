"""R9.1 fake-local autonomous execution boundary demonstration."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import ActionProposal, ChallengeSpec, RunState, ToolCall
from agent.tools.registry import build_default_registry
from agent.tools.runtime import ToolRuntime, ToolRuntimeExecutor
from agent.workspace.manager import WorkspaceManager


DEMO_TOKEN = "LOCAL_AUTONOMOUS_BOUNDARY_OK"


def run_demo(workspace_root: str | Path) -> str:
    manager = WorkspaceManager(workspace_root)
    workspace = manager.create("r91-fake-local")
    (workspace.input_dir / "challenge.txt").write_text(
        "authorized fake local challenge\n",
        encoding="utf-8",
    )
    registry = build_default_registry()
    executor = ToolRuntimeExecutor(
        ToolRuntime(
            registry,
            PolicyEngine(),
            ApprovalManager(),
        ),
        manager,
        execution_mode="autonomous_local",
    )
    state = RunState(
        ChallengeSpec(
            challenge_id="r91-fake-local",
            title="R9.1 fake local boundary",
            description="Inspect one explicitly authorized local fixture.",
            authorization_scope="authorized_local_demo",
        ),
        run_id="r91-local-run",
    )
    proposal = ActionProposal(
        objective="inspect the contained fake challenge without a host shell",
        reasoning_summary="exercise only the R9.1 local autonomous boundary",
        actions=[
            ToolCall("list-input", "workspace_list", {"path": "workspace://input"}),
            ToolCall(
                "read-input",
                "workspace_read_text",
                {"path": "workspace://input/challenge.txt"},
            ),
            ToolCall("deny-bash", "bash", {"command": "pwd"}),
        ],
    )
    executor.prepare(state, 1, proposal)
    results = executor.execute(proposal)
    if not results[0].success or "challenge.txt" not in results[0].stdout:
        raise RuntimeError("workspace_list did not observe the fake input")
    if not results[1].success or "authorized fake local" not in results[1].stdout:
        raise RuntimeError("workspace_read_text did not read the fake input")
    if results[2].success or "not permitted" not in (results[2].error or ""):
        raise RuntimeError("bash was not denied in autonomous_local mode")
    return DEMO_TOKEN


def main() -> None:
    with TemporaryDirectory(prefix="agonionce-r91-") as directory:
        print(run_demo(Path(directory) / "workspace"))


if __name__ == "__main__":
    main()
