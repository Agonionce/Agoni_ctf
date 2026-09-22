from __future__ import annotations

import json
import subprocess

import pytest

from agent.artifacts.store import ArtifactStore
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyDecisionType, PolicyEngine
from agent.runtime.contracts import ActionProposal, ToolCall
from agent.sandbox.docker import DockerBackend
from agent.sandbox.manager import SandboxManager
from agent.sandbox.models import (
    DockerAvailability,
    SandboxConfigurationError,
    SandboxMount,
    SandboxResult,
    SandboxSpec,
)
from agent.sandbox.policy import SandboxPolicy
from agent.tools.contracts import ExecutionContext
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime
from agent.tools.sandbox_python import SandboxPythonTool
from agent.workspace.manager import WorkspaceManager


CONTAINER_ID = "a" * 64


def _completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def _workspace_context(tmp_path, mode="autonomous_local"):
    workspace = WorkspaceManager(tmp_path / "workspace").create("r92-sandbox")
    context = ExecutionContext(
        run_id="run-r92",
        challenge_id="r92-sandbox",
        step_id=1,
        workspace_root=workspace.root,
        input_dir=workspace.input_dir,
        work_dir=workspace.work_dir,
        output_dir=workspace.output_dir,
        logs_dir=workspace.logs_dir,
        objective="validate a local sandbox",
        reasoning_summary="deterministic R9.2 test",
        execution_mode=mode,
    )
    return workspace, context


def _workspace_spec(workspace, **overrides):
    values = {
        "image": "python:test-local",
        "network": "none",
        "cpu_limit": 1.0,
        "memory_limit": "128m",
        "timeout": 2.0,
        "mounts": SandboxPolicy().workspace_mounts(
            input_dir=workspace.input_dir,
            work_dir=workspace.work_dir,
            output_dir=workspace.output_dir,
        ),
    }
    values.update(overrides)
    return SandboxSpec(**values)


def test_sandbox_spec_enforces_safe_resource_and_network_contract(tmp_path):
    workspace, _context = _workspace_context(tmp_path)
    spec = _workspace_spec(workspace)

    assert spec.network == "none"
    assert spec.cpu_limit == 1.0
    assert spec.memory_limit == "128m"
    assert {mount.target for mount in spec.mounts} == {
        "/workspace/input",
        "/workspace/work",
        "/workspace/output",
    }
    with pytest.raises(SandboxConfigurationError, match="networking"):
        _workspace_spec(workspace, network="host")
    with pytest.raises(SandboxConfigurationError, match="image"):
        _workspace_spec(workspace, image="--privileged")
    with pytest.raises(SandboxConfigurationError, match="cpu_limit"):
        _workspace_spec(workspace, cpu_limit=0)
    with pytest.raises(SandboxConfigurationError, match="cpu_limit"):
        _workspace_spec(workspace, cpu_limit="1")
    with pytest.raises(SandboxConfigurationError, match="memory_limit"):
        _workspace_spec(workspace, memory_limit="unlimited")
    with pytest.raises(SandboxConfigurationError, match="timeout"):
        _workspace_spec(workspace, timeout=301)


def test_sandbox_policy_rejects_host_mounts_and_requires_input_read_only(tmp_path):
    workspace, _context = _workspace_context(tmp_path)
    policy = SandboxPolicy()
    spec = _workspace_spec(workspace)
    policy.validate(
        spec,
        workspace_root=workspace.root,
        input_dir=workspace.input_dir,
        work_dir=workspace.work_dir,
        output_dir=workspace.output_dir,
    )

    outside = tmp_path / "host-data"
    outside.mkdir()
    host_mount_spec = _workspace_spec(
        workspace,
        mounts=(
            SandboxMount(outside, "/workspace/input", True),
            SandboxMount(workspace.work_dir, "/workspace/work", False),
            SandboxMount(workspace.output_dir, "/workspace/output", False),
        ),
    )
    with pytest.raises(SandboxConfigurationError, match="mount source"):
        policy.validate(
            host_mount_spec,
            workspace_root=workspace.root,
            input_dir=workspace.input_dir,
            work_dir=workspace.work_dir,
            output_dir=workspace.output_dir,
        )
    writable_input_spec = _workspace_spec(
        workspace,
        mounts=(
            SandboxMount(workspace.input_dir, "/workspace/input", False),
            SandboxMount(workspace.work_dir, "/workspace/work", False),
            SandboxMount(workspace.output_dir, "/workspace/output", False),
        ),
    )
    with pytest.raises(SandboxConfigurationError, match="read-only"):
        policy.validate(
            writable_input_spec,
            workspace_root=workspace.root,
            input_dir=workspace.input_dir,
            work_dir=workspace.work_dir,
            output_dir=workspace.output_dir,
        )
    with pytest.raises(SandboxConfigurationError, match="workspace directories"):
        policy.validate(
            spec,
            workspace_root=workspace.root,
            input_dir=workspace.work_dir,
            work_dir=workspace.input_dir,
            output_dir=workspace.output_dir,
        )


def test_docker_availability_distinguishes_client_and_daemon():
    def daemon_down(command, **_kwargs):
        if command[1] == "--version":
            return _completed(command, stdout="Docker version test\n")
        return _completed(command, returncode=1, stderr="daemon unavailable")

    availability = DockerBackend(
        executable="docker",
        runner=daemon_down,
    ).check()

    assert availability.client_available is True
    assert availability.daemon_available is False
    assert availability.available is False
    assert availability.error == "daemon unavailable"


def test_docker_availability_rejects_remote_context():
    def remote_context(command, **_kwargs):
        if command[1] == "--version":
            return _completed(command, stdout="Docker version test\n")
        if command[1:3] == ["context", "show"]:
            return _completed(command, stdout="remote-test\n")
        if command[1:3] == ["context", "inspect"]:
            return _completed(command, stdout="ssh://ctf-host\n")
        raise AssertionError(f"unexpected Docker command: {command}")

    availability = DockerBackend(
        executable="docker",
        runner=remote_context,
    ).check()

    assert availability.client_available is True
    assert availability.daemon_available is False
    assert "remote" in availability.error


def test_docker_availability_rejects_remote_environment(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote.example:2376")

    availability = DockerBackend(
        executable="docker",
        runner=lambda command, **_kwargs: _completed(
            command,
            stdout="Docker version test\n",
        ),
    ).check()

    assert availability.client_available is True
    assert availability.daemon_available is False
    assert "DOCKER_HOST" in availability.error


def test_docker_lifecycle_uses_only_safe_mounts_and_cleans_up_on_timeout(tmp_path):
    workspace, _context = _workspace_context(tmp_path)
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        operation = command[1]
        if operation == "--version":
            return _completed(command, stdout="Docker version test\n")
        if operation == "context" and command[2] == "show":
            return _completed(command, stdout="local-test\n")
        if operation == "context" and command[2] == "inspect":
            return _completed(command, stdout="unix:///tmp/docker-test.sock\n")
        if operation == "info":
            return _completed(command, stdout="test-server\n")
        if operation == "image":
            return _completed(command, stdout="[]")
        if operation == "create":
            return _completed(command, stdout=CONTAINER_ID + "\n")
        if operation == "start":
            raise subprocess.TimeoutExpired(
                command,
                kwargs["timeout"],
                output="partial stdout",
                stderr="partial stderr",
            )
        if operation == "rm":
            return _completed(command, stdout=CONTAINER_ID + "\n")
        raise AssertionError(f"unexpected Docker operation: {operation}")

    manager = SandboxManager(
        DockerBackend(
            executable="docker",
            runner=runner,
            user_id=1000,
            group_id=1000,
        ),
    )
    spec = _workspace_spec(workspace, timeout=0.5)

    result = manager.execute(
        spec,
        ["python3", "-I", "/workspace/input/test.py"],
        workspace_root=workspace.root,
        input_dir=workspace.input_dir,
        work_dir=workspace.work_dir,
        output_dir=workspace.output_dir,
    )

    assert result.success is False
    assert result.timed_out is True
    assert result.exit_code == 124
    assert result.stdout == "partial stdout"
    assert any(command[1:3] == ["rm", "--force"] for command, _kwargs in calls)
    create = next(command for command, _kwargs in calls if command[1] == "create")
    assert create[create.index("--network") + 1] == "none"
    assert "--privileged" not in create
    assert "--read-only" in create
    assert create[create.index("--cap-drop") + 1] == "ALL"
    assert create[create.index("--security-opt") + 1] == "no-new-privileges"
    assert create[create.index("--user") + 1] == "1000:1000"
    mount_values = [
        create[index + 1]
        for index, value in enumerate(create)
        if value == "--mount"
    ]
    assert len(mount_values) == 3
    assert any("dst=/workspace/input,readonly" in value for value in mount_values)
    assert any("dst=/workspace/work" in value for value in mount_values)
    assert any("dst=/workspace/output" in value for value in mount_values)
    assert all("docker.sock" not in value for value in mount_values)


class _SuccessfulBackend:
    def check(self):
        return DockerAvailability(True, True, version="fake")

    def image_available(self, image):
        return image == "python:test-local"

    def create(self, spec, command):
        self.spec = spec
        self.command = command
        return CONTAINER_ID

    def run(self, container_id, spec):
        return SandboxResult(
            success=True,
            stdout="LOCAL_SANDBOX_TEST_OK\n",
            stderr="",
            exit_code=0,
            duration=0.125,
            timed_out=False,
            container_id=container_id,
            spec=spec,
        )

    def cleanup(self, container_id):
        assert container_id == CONTAINER_ID
        return True, ""


def test_sandbox_python_flows_through_policy_and_registers_execution_artifact(tmp_path):
    workspace, context = _workspace_context(tmp_path)
    script = workspace.input_dir / "test.py"
    script.write_text("print('fixture')\n", encoding="utf-8")
    backend = _SuccessfulBackend()
    manager = SandboxManager(backend)
    registry = ToolRegistry()
    registry.register(SandboxPythonTool(manager, image="python:test-local"))
    runtime = ToolRuntime(registry, PolicyEngine(), ApprovalManager())
    store = ArtifactStore(workspace)
    proposal = ActionProposal(
        "execute a contained test script",
        "exercise ToolRuntime before SandboxManager",
        [
            ToolCall(
                "sandbox",
                "sandbox_python",
                {"script": "workspace://input/test.py", "timeout": 2},
            )
        ],
    )

    result = runtime.execute(proposal, context, store)[0]

    assert result.success is True
    assert result.policy_decision["decision"] == PolicyDecisionType.ALLOW.value
    assert result.stdout == "LOCAL_SANDBOX_TEST_OK\n"
    assert backend.command == [
        "python3",
        "-I",
        "/workspace/input/test.py",
    ]
    assert result.metadata["sandbox"]["network"] == "none"
    assert result.metadata["sandbox"]["cleanup_succeeded"] is True
    assert result.artifact_refs == ["artifact-001"]
    artifact = store.get("artifact-001")
    assert artifact is not None
    assert artifact.artifact_type == "sandbox_execution"
    artifact_payload = json.loads((workspace.root / artifact.path).read_text(encoding="utf-8"))
    assert artifact_payload["stdout"] == "LOCAL_SANDBOX_TEST_OK\n"
    assert artifact_payload["stderr"] == ""
    assert artifact_payload["exit_code"] == 0
    assert artifact_payload["duration"] == 0.125
    assert artifact_payload["sandbox"]["network"] == "none"
    assert str(workspace.root) not in json.dumps(artifact_payload)


def test_sandbox_python_is_autonomous_but_host_python_remains_denied(tmp_path):
    _workspace, context = _workspace_context(tmp_path)
    manager = SandboxManager(_SuccessfulBackend())
    sandbox_tool = SandboxPythonTool(manager)
    from agent.tools.builtin import PythonExecutionTool

    sandbox_decision = PolicyEngine().evaluate(
        ToolCall(
            "sandbox",
            "sandbox_python",
            {"script": "workspace://input/test.py"},
        ),
        sandbox_tool.metadata,
        context,
    )
    host_decision = PolicyEngine().evaluate(
        ToolCall(
            "host",
            "python",
            {"script": "workspace://input/test.py"},
        ),
        PythonExecutionTool.metadata,
        context,
    )

    assert sandbox_decision.decision is PolicyDecisionType.ALLOW
    assert host_decision.decision is PolicyDecisionType.DENY
