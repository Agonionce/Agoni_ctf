"""R1 ToolRuntime: policy, action approval, execution and audit lifecycle."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.artifacts.store import ArtifactStore
from agent.policy.approval import ApprovalManager, ApprovalRequest, ApprovalStatus
from agent.policy.engine import PolicyDecision, PolicyDecisionType, PolicyEngine
from agent.runtime.contracts import ActionProposal, RunState, ToolCall, ToolResult
from agent.tools.contracts import ExecutionContext, ToolError
from agent.tools.registry import ToolRegistry
from agent.tools.settings import ExecutionMode
from agent.tools.validation import ToolArgumentValidator
from agent.workspace.manager import Workspace, WorkspaceManager


@dataclass
class ToolAuditRecord:
    execution_id: str
    caller: str
    run_id: str
    challenge_id: str
    step_id: int
    call_id: str
    tool_name: str
    objective: str
    reasoning_summary: str
    arguments: Dict[str, Any]
    policy_decision: Dict[str, str]
    started_at: str
    finished_at: str
    success: bool
    exit_code: int | None
    stdout: str
    stderr: str
    error: str | None
    metadata: Dict[str, Any]
    artifact_refs: List[str]
    tool: str
    arguments_hash: str
    policy_result: str
    execution_mode: str
    timestamp: str


class ToolRuntime:
    """Execute registered Tools only after independent policy evaluation."""

    def __init__(
        self,
        registry: ToolRegistry,
        policy_engine: PolicyEngine,
        approval_manager: ApprovalManager,
        approval_resolver: Optional[Callable[[ApprovalRequest], bool]] = None,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        self.registry = registry
        self.policy_engine = policy_engine
        self.approval_manager = approval_manager
        self.approval_resolver = approval_resolver
        self.event_callback = event_callback
        self.audit_records: List[ToolAuditRecord] = []

    def execute(
        self,
        proposal: ActionProposal,
        context: ExecutionContext,
        artifact_store: ArtifactStore,
    ) -> List[ToolResult]:
        return [
            self.execute_call(call, proposal, context, artifact_store)
            for call in proposal.actions
        ]

    def execute_call(
        self,
        call: ToolCall,
        proposal: ActionProposal,
        context: ExecutionContext,
        artifact_store: ArtifactStore,
    ) -> ToolResult:
        started_at = datetime.now(timezone.utc)
        started_clock = time.monotonic()
        tool = self.registry.get(call.tool_name)
        if tool is None:
            decision = PolicyDecision(
                PolicyDecisionType.DENY,
                f"unregistered tool: {call.tool_name}",
                risk_level=self._unknown_risk(),
            )
            return self._result_and_audit(
                call, proposal, context, started_at, started_clock, False,
                error=decision.reason, decision=decision,
            )

        schema_error = ToolArgumentValidator.validate(
            call.arguments,
            tool.input_schema,
        )
        if schema_error is not None:
            return self._result_and_audit(
                call,
                proposal,
                context,
                started_at,
                started_clock,
                False,
                error=schema_error.message,
                decision=None,
                tool_error=schema_error,
            )

        decision = self.policy_engine.evaluate(call, tool.metadata, context)
        if decision.decision is PolicyDecisionType.DENY:
            self._emit_approval_event(call, decision, context, "DENIED")
            return self._result_and_audit(
                call, proposal, context, started_at, started_clock, False,
                error=decision.reason, decision=decision,
            )

        if decision.decision is PolicyDecisionType.REQUIRE_APPROVAL:
            request = self.approval_manager.request(
                tool_name=call.tool_name,
                arguments=call.arguments,
                reason=proposal.reasoning_summary,
                risk_level=decision.risk_level.value,
            )
            if self.approval_resolver is None:
                self.approval_manager.reject(request.request_id, "no approval resolver")
            elif self.approval_resolver(request):
                self.approval_manager.approve(request.request_id)
            else:
                self.approval_manager.reject(request.request_id, "user rejected action")
            request = self.approval_manager.get(request.request_id)
            assert request is not None
            self._emit_approval_event(
                call,
                decision,
                context,
                request.status.value,
                request_id=request.request_id,
            )
            if request.status is not ApprovalStatus.APPROVED:
                return self._result_and_audit(
                    call, proposal, context, started_at, started_clock, False,
                    error="approval required and not granted", decision=decision,
                )
        else:
            self._emit_approval_event(call, decision, context, "NOT_REQUIRED")

        try:
            output = tool.execute(call.arguments, context)
        except Exception as error:  # tool boundary normalizes backend errors
            return self._result_and_audit(
                call, proposal, context, started_at, started_clock, False,
                error=str(error), decision=decision,
            )

        artifact_refs: List[str] = []
        for artifact_path in output.artifact_paths:
            artifact_type = output.artifact_types.get(
                str(artifact_path),
                output.artifact_type,
            )
            artifact = artifact_store.register(
                artifact_path,
                created_by=call.tool_name,
                source_step=context.step_id,
                artifact_type=artifact_type,
            )
            artifact_refs.append(artifact.artifact_id)
        return self._result_and_audit(
            call,
            proposal,
            context,
            started_at,
            started_clock,
            output.success,
            stdout=output.stdout,
            stderr=output.stderr,
            exit_code=output.exit_code,
            error=output.error,
            artifact_refs=artifact_refs,
            metadata=output.metadata,
            decision=decision,
        )

    @staticmethod
    def _unknown_risk():
        from agent.tools.contracts import ToolRiskLevel

        return ToolRiskLevel.HIGH

    def _result_and_audit(
        self,
        call: ToolCall,
        proposal: ActionProposal,
        context: ExecutionContext,
        started_at: datetime,
        started_clock: float,
        success: bool,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        error: str | None = None,
        artifact_refs: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        decision: PolicyDecision | None,
        tool_error: ToolError | None = None,
    ) -> ToolResult:
        finished_at = datetime.now(timezone.utc)
        artifact_refs = artifact_refs or []
        execution_context = {
            "run_id": context.run_id,
            "challenge_id": context.challenge_id,
            "step_id": context.step_id,
            "workspace_root": str(context.workspace_root),
            "objective": context.objective,
        }
        result_metadata = dict(metadata or {})
        if tool_error is not None:
            result_metadata["tool_error"] = tool_error.to_dict()
        policy_decision = (
            decision.to_dict()
            if decision is not None
            else {
                "decision": "NOT_EVALUATED",
                "reason": "tool argument schema validation failed",
                "risk_level": "HIGH",
            }
        )
        result = ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
            duration=max(0.0, time.monotonic() - started_clock),
            metadata=result_metadata,
            artifact_refs=artifact_refs,
            execution_context=execution_context,
            policy_decision=policy_decision,
            tool_error=tool_error.to_dict() if tool_error is not None else None,
        )
        safe_arguments = self._redact(call.arguments)
        safe_metadata = self._redact(result_metadata)
        safe_policy = self._redact(policy_decision)
        audit = ToolAuditRecord(
            execution_id=str(uuid.uuid4()),
            caller="AgentRuntime",
            run_id=context.run_id,
            challenge_id=context.challenge_id,
            step_id=context.step_id,
            call_id=call.call_id,
            tool_name=call.tool_name,
            objective=str(self._redact(context.objective)),
            reasoning_summary=str(self._redact(context.reasoning_summary)),
            arguments=safe_arguments if isinstance(safe_arguments, dict) else {},
            policy_decision=safe_policy if isinstance(safe_policy, dict) else {},
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            success=success,
            exit_code=exit_code,
            stdout=str(self._redact(stdout)),
            stderr=str(self._redact(stderr)),
            error=str(self._redact(error)) if error is not None else None,
            metadata=safe_metadata if isinstance(safe_metadata, dict) else {},
            artifact_refs=artifact_refs,
            tool=call.tool_name,
            arguments_hash=self._arguments_hash(call.arguments),
            policy_result=policy_decision["decision"],
            execution_mode=context.execution_mode,
            timestamp=started_at.isoformat(),
        )
        self.audit_records.append(audit)
        self._append_audit(context.logs_dir / "tool-audit.jsonl", audit)
        return result

    @staticmethod
    def _append_audit(path: Path, audit: ToolAuditRecord) -> None:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(audit), ensure_ascii=False) + "\n")

    def _emit_approval_event(
        self,
        call: ToolCall,
        decision: PolicyDecision,
        context: ExecutionContext,
        approval_status: str,
        *,
        request_id: str = "",
    ) -> None:
        if self.event_callback is None:
            return
        self.event_callback(
            "tool_approval",
            {
                "run_id": context.run_id,
                "step_id": context.step_id,
                "call_id": call.call_id,
                "tool": call.tool_name,
                "arguments_hash": self._arguments_hash(call.arguments),
                "policy_result": decision.decision.value,
                "approval_status": approval_status,
                "request_id": request_id,
                "execution_mode": context.execution_mode,
            },
        )

    @staticmethod
    def _arguments_hash(arguments: Dict[str, Any]) -> str:
        payload = json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _redact(cls, value: Any, key: str = "") -> Any:
        sensitive_names = (
            "cookie",
            "token",
            "password",
            "passwd",
            "secret",
            "flag",
            "credential",
            "authorization",
            "api_key",
        )
        normalized_key = key.lower().replace("-", "_")
        if normalized_key and any(name in normalized_key for name in sensitive_names):
            return "<redacted>"
        if isinstance(value, dict):
            return {
                str(item_key): cls._redact(item_value, str(item_key))
                for item_key, item_value in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [cls._redact(item, key) for item in value]
        if isinstance(value, str):
            redacted = re.sub(
                r"(?i)\b(?:flag|ctf)\{[^}\r\n]+\}",
                "<redacted>",
                value,
            )
            return re.sub(
                r"(?i)\b(password|passwd|token|cookie|secret|credential|api[_-]?key)"
                r"\s*[:=]\s*([^\s,;]+)",
                r"\1=<redacted>",
                redacted,
            )
        return value


class ToolRuntimeExecutor:
    """R0 Executor adapter; Runtime supplies state before each step."""

    def __init__(
        self,
        tool_runtime: ToolRuntime,
        workspace_manager: WorkspaceManager,
        execution_mode: str = ExecutionMode.MANUAL.value,
    ) -> None:
        self.tool_runtime = tool_runtime
        self.workspace_manager = workspace_manager
        self.execution_mode = ExecutionMode(execution_mode).value
        self._context: Optional[ExecutionContext] = None
        self._artifact_stores: Dict[Path, ArtifactStore] = {}

    def prepare(self, state: RunState, step_id: int, proposal: ActionProposal) -> None:
        workspace = self.workspace_manager.create(state.challenge.challenge_id)
        raw_targets = state.challenge.metadata.get("authorized_targets", [])
        authorized_targets = (
            [str(item) for item in raw_targets]
            if isinstance(raw_targets, list)
            else []
        )
        base_url = state.challenge.metadata.get("base_url")
        if isinstance(base_url, str) and base_url:
            authorized_targets.append(base_url)
        self._context = ExecutionContext(
            run_id=state.run_id,
            challenge_id=state.challenge.challenge_id,
            step_id=step_id,
            workspace_root=workspace.root,
            input_dir=workspace.input_dir,
            work_dir=workspace.work_dir,
            output_dir=workspace.output_dir,
            logs_dir=workspace.logs_dir,
            objective=proposal.objective,
            reasoning_summary=proposal.reasoning_summary,
            authorized_targets=tuple(dict.fromkeys(authorized_targets)),
            execution_mode=self.execution_mode,
        )

    def execute(self, proposal: ActionProposal) -> List[ToolResult]:
        if self._context is None:
            raise RuntimeError("ToolRuntimeExecutor.prepare must run before execute")
        store = self._artifact_stores.get(self._context.workspace_root)
        if store is None:
            workspace = Workspace(
                challenge_id=self._context.challenge_id,
                root=self._context.workspace_root,
                input_dir=self._context.input_dir,
                work_dir=self._context.work_dir,
                output_dir=self._context.output_dir,
                logs_dir=self._context.logs_dir,
            )
            store = ArtifactStore(workspace)
            self._artifact_stores[self._context.workspace_root] = store
        return self.tool_runtime.execute(proposal, self._context, store)

    def artifacts_for_current_workspace(self) -> List[Any]:
        if self._context is None:
            return []
        store = self._artifact_stores.get(self._context.workspace_root)
        return store.list() if store is not None else []
