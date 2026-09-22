"""R9.2 real local Docker sandbox demonstration."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import ActionProposal, ChallengeSpec, RunState, ToolCall
from agent.sandbox.manager import SandboxManager
from agent.tools.registry import build_default_registry
from agent.tools.runtime import ToolRuntime, ToolRuntimeExecutor
from agent.workspace.manager import WorkspaceManager


DEMO_TOKEN = "LOCAL_SANDBOX_OK"
SANDBOX_IMAGE = "python:3.12-alpine"


def run_demo(workspace_root: str | Path) -> str:
    sandbox_manager = SandboxManager()
    availability = sandbox_manager.check()
    if not availability.available:
        raise RuntimeError(
            "Docker daemon is unavailable; start the local Docker daemon before running R9.2 demo"
        )
    if not sandbox_manager.image_available(SANDBOX_IMAGE):
        raise RuntimeError(
            f"required local image is absent: {SANDBOX_IMAGE}; R9.2 never pulls images automatically"
        )

    workspace_manager = WorkspaceManager(workspace_root)
    workspace = workspace_manager.create("r92-local-sandbox")
    (workspace.input_dir / "sandbox_demo.py").write_text(
        "from pathlib import Path\n"
        "ipv4_routes = Path('/proc/net/route').read_text().splitlines()[1:]\n"
        "if ipv4_routes:\n"
        "    raise RuntimeError('unexpected sandbox IPv4 route')\n"
        "ipv6_routes = Path('/proc/net/ipv6_route').read_text().splitlines()\n"
        "if any(route.split()[-1] != 'lo' for route in ipv6_routes):\n"
        "    raise RuntimeError('unexpected sandbox IPv6 route')\n"
        "try:\n"
        "    Path('/workspace/input/mutation.txt').write_text('forbidden')\n"
        "except OSError:\n"
        "    pass\n"
        "else:\n"
        "    raise RuntimeError('input mount is writable')\n"
        "Path('/workspace/output/container-result.txt').write_text('contained output')\n"
        f"print({DEMO_TOKEN!r})\n",
        encoding="utf-8",
    )
    executor = ToolRuntimeExecutor(
        ToolRuntime(
            build_default_registry(sandbox_manager),
            PolicyEngine(),
            ApprovalManager(),
        ),
        workspace_manager,
        execution_mode="autonomous_local",
    )
    state = RunState(
        ChallengeSpec(
            challenge_id="r92-local-sandbox",
            title="R9.2 authorized local sandbox",
            description="Run a deterministic fixture with Docker networking disabled.",
            authorization_scope="authorized_local_demo",
        ),
        run_id="r92-local-sandbox-run",
    )
    proposal = ActionProposal(
        objective="execute one authorized fixture inside the local sandbox",
        reasoning_summary="validate the R9.2 controlled Docker execution path",
        actions=[
            ToolCall(
                "sandbox-python",
                "sandbox_python",
                {
                    "script": "workspace://input/sandbox_demo.py",
                    "timeout": 10,
                },
            )
        ],
    )
    executor.prepare(state, 1, proposal)
    result = executor.execute(proposal)[0]
    if not result.success or DEMO_TOKEN not in result.stdout:
        raise RuntimeError(result.stderr or result.error or "sandbox demo failed")
    sandbox_metadata = result.metadata.get("sandbox", {})
    if sandbox_metadata.get("network") != "none":
        raise RuntimeError("sandbox demo did not preserve the network-disabled contract")
    if not result.artifact_refs:
        raise RuntimeError("sandbox demo did not register its execution artifact")
    if (
        workspace.output_dir / "container-result.txt"
    ).read_text(encoding="utf-8") != "contained output":
        raise RuntimeError("sandbox output mount did not retain the contained result")
    if (workspace.input_dir / "mutation.txt").exists():
        raise RuntimeError("sandbox input mount was unexpectedly modified")
    return DEMO_TOKEN


def main() -> None:
    with TemporaryDirectory(prefix="agonionce-r92-") as directory:
        print(run_demo(Path(directory) / "workspace"))


if __name__ == "__main__":
    main()
