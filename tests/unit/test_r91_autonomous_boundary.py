from __future__ import annotations

import json
from datetime import datetime, timezone
from zipfile import ZipFile

import pytest

from agent.artifacts.store import ArtifactStore
from agent.intelligence.checkpoint import IntelligenceCheckpoint, RuntimeStepCheckpoint
from agent.intelligence.store import IntelligenceStore
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyDecisionType, PolicyEngine
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    RunBudget,
    RunState,
    RunStatus,
    ToolCall,
    ToolResult,
)
from agent.runtime.runtime import AgentRuntime
from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
    ToolRiskLevel,
)
from agent.tools.registry import ToolRegistry, build_default_registry
from agent.tools.runtime import ToolRuntime
from agent.tools.settings import ExecutionSettings
from agent.workspace.manager import WorkspaceManager
from agent.workspace.path import WorkspacePathResolver


def _context(tmp_path, mode: str = "manual"):
    workspace = WorkspaceManager(tmp_path / "workspace").create("r91-policy")
    return workspace, ExecutionContext(
        run_id="run-r91",
        challenge_id="r91-policy",
        step_id=1,
        workspace_root=workspace.root,
        input_dir=workspace.input_dir,
        work_dir=workspace.work_dir,
        output_dir=workspace.output_dir,
        logs_dir=workspace.logs_dir,
        objective="test the execution boundary",
        reasoning_summary="deterministic R9.1 unit test",
        execution_mode=mode,
    )


def test_workspace_uri_contract_resolves_scopes_and_rejects_traversal(tmp_path):
    workspace = WorkspaceManager(tmp_path / "workspace").create("path-contract")
    target = workspace.input_dir / "a.txt"
    target.write_text("fixture", encoding="utf-8")
    resolver = WorkspacePathResolver(workspace.root)

    resolved = resolver.resolve("workspace://input/a.txt")

    assert resolved.path == target
    assert resolved.uri == "workspace://input/a.txt"
    assert resolver.resolve("input/a.txt").path == target
    with pytest.raises(ValueError, match="traversal"):
        resolver.resolve("workspace://input/../../secret")
    with pytest.raises(ValueError, match="traversal"):
        resolver.resolve("../../secret")
    with pytest.raises(ValueError, match="scope"):
        resolver.resolve("workspace://logs/tool-audit.jsonl")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = workspace.input_dir / "escape-link"
    try:
        link.symlink_to(outside)
    except OSError:
        pass
    else:
        with pytest.raises(ValueError, match="escapes"):
            resolver.resolve("workspace://input/escape-link")


@pytest.mark.parametrize("mode", ["manual", "supervised", "autonomous_local"])
def test_execution_settings_accept_all_r91_modes(mode):
    settings = ExecutionSettings.from_mapping({"mode": mode})
    assert settings.mode == mode


def test_autonomous_local_allows_structured_read_and_denies_bash(tmp_path):
    _workspace, context = _context(tmp_path, "autonomous_local")
    registry = build_default_registry()
    structured = registry.get("workspace_list")
    writer = registry.get("workspace_write_text")
    bash = registry.get("bash")
    assert structured is not None and writer is not None and bash is not None

    structured_decision = PolicyEngine().evaluate(
        ToolCall("list", "workspace_list", {"path": "workspace://input"}),
        structured.metadata,
        context,
    )
    bash_decision = PolicyEngine().evaluate(
        ToolCall("bash", "bash", {"command": "pwd"}),
        bash.metadata,
        context,
    )
    input_write_decision = PolicyEngine().evaluate(
        ToolCall(
            "write-input",
            "workspace_write_text",
            {"path": "workspace://input/immutable.txt", "content": "no"},
        ),
        writer.metadata,
        context,
    )

    assert structured_decision.decision is PolicyDecisionType.ALLOW
    assert bash_decision.decision is PolicyDecisionType.DENY
    assert input_write_decision.decision is PolicyDecisionType.DENY


@pytest.mark.parametrize("mode", ["manual", "supervised"])
def test_manual_and_supervised_require_approval_for_host_process_tools(tmp_path, mode):
    _workspace, context = _context(tmp_path, mode)
    registry = build_default_registry()
    bash = registry.get("bash")
    python = registry.get("python")
    assert bash is not None and python is not None

    bash_decision = PolicyEngine().evaluate(
        ToolCall("bash", "bash", {"command": "pwd"}),
        bash.metadata,
        context,
    )
    python_decision = PolicyEngine().evaluate(
        ToolCall("python", "python", {"script": "workspace://work/solve.py"}),
        python.metadata,
        context,
    )

    assert bash_decision.decision is PolicyDecisionType.REQUIRE_APPROVAL
    assert python_decision.decision is PolicyDecisionType.REQUIRE_APPROVAL


def test_tool_schema_failure_is_structured_and_precedes_policy(tmp_path):
    workspace, context = _context(tmp_path, "autonomous_local")
    runtime = ToolRuntime(
        build_default_registry(),
        PolicyEngine(),
        ApprovalManager(),
    )
    proposal = ActionProposal(
        "reject invalid arguments",
        "schema validation must happen before policy",
        [ToolCall("invalid", "workspace_list", {"path": 42})],
    )

    result = runtime.execute(proposal, context, ArtifactStore(workspace))[0]

    assert result.success is False
    assert result.policy_decision["decision"] == "NOT_EVALUATED"
    assert result.tool_error is not None
    assert result.tool_error["code"] == "TOOL_ARGUMENT_SCHEMA_ERROR"
    assert result.metadata["tool_error"]["code"] == "TOOL_ARGUMENT_SCHEMA_ERROR"
    assert result.metadata["tool_error"]["field_path"] == "$.path"


def test_structured_workspace_tools_read_write_hash_bytes_and_archive(tmp_path):
    workspace, context = _context(tmp_path, "autonomous_local")
    text = workspace.input_dir / "note.txt"
    text.write_text("hello workspace", encoding="utf-8")
    archive = workspace.input_dir / "bundle.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("inside.txt", "metadata only")
    runtime = ToolRuntime(
        build_default_registry(),
        PolicyEngine(),
        ApprovalManager(),
    )
    proposal = ActionProposal(
        "exercise structured workspace capabilities",
        "use typed local tools without a host shell",
        [
            ToolCall("read", "workspace_read_text", {"path": "workspace://input/note.txt"}),
            ToolCall(
                "bytes",
                "workspace_read_bytes",
                {"path": "workspace://input/note.txt", "offset": 0, "length": 5},
            ),
            ToolCall("hash", "file_hash", {"path": "workspace://input/note.txt"}),
            ToolCall("archive", "archive_list", {"path": "workspace://input/bundle.zip"}),
            ToolCall(
                "write",
                "workspace_write_text",
                {"path": "workspace://output/result.txt", "content": "local result"},
            ),
        ],
    )

    results = runtime.execute(proposal, context, ArtifactStore(workspace))

    assert all(result.success for result in results)
    assert results[0].stdout == "hello workspace"
    assert json.loads(results[1].stdout)["hex_preview"] == "68656c6c6f"
    assert len(json.loads(results[2].stdout)["digest"]) == 64
    assert json.loads(results[3].stdout)["entries"][0]["name"] == "inside.txt"
    assert results[4].artifact_refs == ["artifact-001"]
    assert (workspace.output_dir / "result.txt").read_text(encoding="utf-8") == "local result"
    assert not (workspace.work_dir / "inside.txt").exists()


def test_audit_fields_are_complete_and_sensitive_values_are_redacted(tmp_path):
    class SensitiveFakeTool(Tool):
        metadata = ToolMetadata(
            name="sensitive_fake",
            description="test-only redaction fixture",
            risk_level=ToolRiskLevel.LOW,
            requires_network=False,
            writes_files=False,
            execution_type="fake",
            autonomous_allowed=True,
        )
        input_schema = {
            "type": "object",
            "properties": {"token": {"type": "string"}},
            "required": ["token"],
            "additionalProperties": False,
        }

        def execute(self, arguments, context):
            del arguments, context
            return ToolExecutionOutput(True, stdout="flag{SYNTHETIC} password=test-only")

    workspace, context = _context(tmp_path, "autonomous_local")
    registry = ToolRegistry()
    registry.register(SensitiveFakeTool())
    runtime = ToolRuntime(registry, PolicyEngine(), ApprovalManager())
    proposal = ActionProposal(
        "verify audit redaction",
        "sensitive values must not enter audit logs",
        [ToolCall("sensitive", "sensitive_fake", {"token": "test-only-token"})],
    )

    result = runtime.execute(proposal, context, ArtifactStore(workspace))[0]
    audit = json.loads(
        (workspace.logs_dir / "tool-audit.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )

    assert result.success is True
    assert audit["run_id"] == context.run_id
    assert audit["step_id"] == context.step_id
    assert audit["tool"] == "sensitive_fake"
    assert len(audit["arguments_hash"]) == 64
    assert audit["policy_result"] == "ALLOW"
    assert audit["execution_mode"] == "autonomous_local"
    assert audit["timestamp"]
    assert audit["arguments"]["token"] == "<redacted>"
    assert "SYNTHETIC" not in audit["stdout"]
    assert "test-only" not in audit["stdout"]


class _OneStepPlanner:
    def plan(self, challenge, state, tool_schemas):
        del challenge, state, tool_schemas
        return ActionProposal(
            "inspect one fake local value",
            "checkpoint the deterministic action",
            [ToolCall("fake", "fake_tool", {})],
        )


class _CountingExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, proposal):
        self.calls += 1
        call = proposal.actions[0]
        now = datetime.now(timezone.utc)
        return [
            ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=True,
                stdout="durable fake result LOCAL_R91_CHECKPOINT_OK",
                started_at=now,
                finished_at=now,
            )
        ]


class _SolvedAnalyzer:
    def analyze(self, observation, state):
        del state
        return AnalysisResult(
            summary="restored tool evidence was analyzed",
            outcome=AnalysisOutcome.PROGRESS,
            flag_candidates=[
                FlagCandidate(
                    "LOCAL_R91_CHECKPOINT_OK",
                    "fake_tool.stdout",
                    1.0,
                    observation.tool_results[0].stdout,
                )
            ],
            confidence=1.0,
        )


class _InterruptAfterToolResult:
    def __init__(self, delegate):
        self.delegate = delegate

    def record(self, stage, *args, **kwargs):
        result = self.delegate.record(stage, *args, **kwargs)
        if stage == "tool_result":
            raise RuntimeError("simulated interruption after durable tool result")
        return result


def test_step_checkpoint_restores_after_tool_result_without_reexecution(tmp_path):
    challenge = ChallengeSpec(
        "r91-checkpoint",
        "R9.1 checkpoint",
        "Authorized fake local checkpoint fixture.",
    )
    store = IntelligenceStore.create(challenge.challenge_id)
    checkpoint = IntelligenceCheckpoint(tmp_path / "checkpoint")
    writer = RuntimeStepCheckpoint(checkpoint, store)
    executor = _CountingExecutor()
    first = AgentRuntime(
        challenge,
        _OneStepPlanner(),
        executor,
        _SolvedAnalyzer(),
        budget=RunBudget(max_steps=2, max_llm_calls=10),
        intelligence_store=store,
        checkpoint_handler=_InterruptAfterToolResult(writer),
    )

    interrupted = first.run()
    restored = checkpoint.load()

    assert interrupted.status is RunStatus.FAILED
    assert restored.step_checkpoint is not None
    assert restored.step_checkpoint.stage == "tool_result"
    assert restored.run_state.current_step == 0
    assert executor.calls == 1

    resumed_writer = RuntimeStepCheckpoint(checkpoint, restored.intelligence_store)
    resumed = AgentRuntime(
        challenge,
        _OneStepPlanner(),
        executor,
        _SolvedAnalyzer(),
        budget=RunBudget(max_steps=2, max_llm_calls=10),
        intelligence_store=restored.intelligence_store,
        initial_state=restored.run_state,
        checkpoint_handler=resumed_writer,
        initial_step_checkpoint=restored.step_checkpoint,
        flag_confirmer=lambda candidate: candidate.value == "LOCAL_R91_CHECKPOINT_OK",
    ).run()

    assert resumed.status is RunStatus.SOLVED
    assert resumed.current_step == 1
    assert executor.calls == 1
    completed = checkpoint.load()
    assert completed.step_checkpoint is not None
    assert completed.step_checkpoint.stage == "step_complete"
