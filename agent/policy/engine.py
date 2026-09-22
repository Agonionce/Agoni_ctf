"""Independent R1 policy evaluation for one ToolCall."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, Optional

from agent.runtime.contracts import ToolCall
from agent.tools.contracts import ExecutionContext, ToolMetadata, ToolRiskLevel
from agent.tools.settings import ExecutionMode
from agent.policy.web_target import is_scoped_local_web_target, validate_local_web_target


class PolicyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass(frozen=True)
class PolicyDecision:
    decision: PolicyDecisionType
    reason: str
    risk_level: ToolRiskLevel

    def to_dict(self) -> Dict[str, str]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "risk_level": self.risk_level.value,
        }


class FilesystemPolicy:
    """Allow only paths resolvable inside the current challenge workspace."""

    def is_allowed_path(self, value: str | Path, context: ExecutionContext) -> bool:
        try:
            context.resolve_workspace_path(value)
        except (OSError, ValueError):
            return False
        return True

    def evaluate(
        self,
        tool_call: ToolCall,
        metadata: ToolMetadata,
        context: ExecutionContext,
    ) -> Optional[PolicyDecision]:
        scope_rules = dict(metadata.path_scope_rules)
        for argument_name in metadata.path_argument_names:
            value = tool_call.arguments.get(argument_name)
            if not isinstance(value, str) or not value:
                return PolicyDecision(
                    PolicyDecisionType.DENY,
                    f"missing or invalid path argument: {argument_name}",
                    ToolRiskLevel.HIGH,
                )
            try:
                context.workspace_path_resolver().resolve(
                    value,
                    allowed_scopes=scope_rules.get(
                        argument_name,
                        ("input", "work", "output"),
                    ),
                )
            except (OSError, ValueError):
                return PolicyDecision(
                    PolicyDecisionType.DENY,
                    "path is outside the allowed workspace scope",
                    ToolRiskLevel.HIGH,
                )
        return None


class TargetPolicy:
    """Target boundary with exact allowlists and an R5 loopback default."""

    def __init__(self, allowed_targets: Iterable[str] = ()) -> None:
        self.allowed_targets = frozenset(allowed_targets)

    def is_allowed_target(
        self,
        target: str,
        authorized_targets: Iterable[str] = (),
    ) -> bool:
        scopes = tuple({*self.allowed_targets, *authorized_targets})
        return is_scoped_local_web_target(target, scopes)


class WebRequestPolicy:
    """Classify one structured HTTP request after target validation."""

    SAFE_GET_HEADERS = frozenset({"accept", "accept-language", "user-agent"})

    def __init__(self, target_policy: TargetPolicy) -> None:
        self.target_policy = target_policy

    def evaluate(
        self,
        tool_call: ToolCall,
        context: ExecutionContext,
    ) -> PolicyDecision:
        target = tool_call.arguments.get("url")
        if not isinstance(target, str):
            return PolicyDecision(
                PolicyDecisionType.DENY,
                "HTTP target is outside the R5 loopback authorization boundary",
                ToolRiskLevel.HIGH,
            )
        validation = validate_local_web_target(target)
        if not validation.allowed or validation.parsed is None:
            return PolicyDecision(
                PolicyDecisionType.DENY,
                validation.reason,
                ToolRiskLevel.HIGH,
            )
        if not self.target_policy.is_allowed_target(
            target,
            context.authorized_targets,
        ):
            return PolicyDecision(
                PolicyDecisionType.DENY,
                "HTTP origin was not declared by the current challenge",
                ToolRiskLevel.HIGH,
            )
        method = str(tool_call.arguments.get("method", "GET")).upper()
        if method not in {"GET", "POST"}:
            return PolicyDecision(
                PolicyDecisionType.DENY,
                f"unsupported HTTP method: {method}",
                ToolRiskLevel.HIGH,
            )
        headers = tool_call.arguments.get("headers", {})
        custom_headers = (
            {str(name).lower() for name in headers}
            if isinstance(headers, dict)
            else {"invalid"}
        )
        has_parameters = bool(tool_call.arguments.get("params")) or bool(
            validation.parsed.query
        )
        has_body = tool_call.arguments.get("body") not in (None, "", {})
        has_cookies = bool(tool_call.arguments.get("cookies"))
        has_session = bool(tool_call.arguments.get("session_id"))
        safe_headers = custom_headers.issubset(self.SAFE_GET_HEADERS)
        if (
            method == "GET"
            and not has_parameters
            and not has_body
            and not has_cookies
            and not has_session
            and safe_headers
        ):
            return PolicyDecision(
                PolicyDecisionType.ALLOW,
                "read-only loopback GET without input payload",
                ToolRiskLevel.LOW,
            )
        return PolicyDecision(
            PolicyDecisionType.REQUIRE_APPROVAL,
            "stateful or input-bearing HTTP request requires action approval",
            ToolRiskLevel.MEDIUM,
        )


class CommandPolicy:
    """Classify basic shell commands without placing checks in an Executor."""

    LOW_COMMANDS = frozenset({"ls", "pwd", "file", "strings", "cat", "grep"})
    MEDIUM_COMMANDS = frozenset({"curl", "wget", "git", "pip", "python", "python3"})
    HIGH_COMMANDS = frozenset({"rm", "sudo", "chmod", "kill", "pkill", "launchctl"})

    def __init__(self, filesystem_policy: FilesystemPolicy) -> None:
        self.filesystem_policy = filesystem_policy

    def evaluate(self, command: str, context: ExecutionContext) -> PolicyDecision:
        if not isinstance(command, str) or not command.strip():
            return PolicyDecision(PolicyDecisionType.DENY, "empty shell command", ToolRiskLevel.HIGH)
        if any(
            marker in command
            for marker in ("$(", "`", ";", "&&", "||", "\n", "|", ">", "<", "&")
        ):
            return PolicyDecision(
                PolicyDecisionType.REQUIRE_APPROVAL,
                "compound shell syntax requires approval",
                ToolRiskLevel.MEDIUM,
            )
        try:
            tokens = shlex.split(command)
        except ValueError:
            return PolicyDecision(
                PolicyDecisionType.REQUIRE_APPROVAL,
                "shell command could not be parsed safely",
                ToolRiskLevel.MEDIUM,
            )
        if not tokens:
            return PolicyDecision(PolicyDecisionType.DENY, "empty shell command", ToolRiskLevel.HIGH)
        executable = Path(tokens[0]).name
        if executable in self.HIGH_COMMANDS:
            return PolicyDecision(
                PolicyDecisionType.DENY,
                f"high-risk command is denied in R1: {executable}",
                ToolRiskLevel.HIGH,
            )
        for token in tokens[1:]:
            path_like = (
                token.startswith("/")
                or token.startswith(".")
                or "/" in token
            )
            if (
                path_like
                and not token.startswith("-")
                and not self.filesystem_policy.is_allowed_path(token, context)
            ):
                return PolicyDecision(
                    PolicyDecisionType.DENY,
                    "shell command references a path outside the challenge workspace",
                    ToolRiskLevel.HIGH,
                )
        if executable in self.MEDIUM_COMMANDS:
            return PolicyDecision(
                PolicyDecisionType.REQUIRE_APPROVAL,
                f"medium-risk command requires approval: {executable}",
                ToolRiskLevel.MEDIUM,
            )
        if executable in self.LOW_COMMANDS:
            return PolicyDecision(
                PolicyDecisionType.REQUIRE_APPROVAL,
                f"host shell command requires manual approval: {executable}",
                ToolRiskLevel.MEDIUM,
            )
        return PolicyDecision(
            PolicyDecisionType.REQUIRE_APPROVAL,
            f"unknown shell command requires approval: {executable}",
            ToolRiskLevel.MEDIUM,
        )


class PolicyEngine:
    """Combine filesystem, command, target and metadata decisions centrally."""

    def __init__(
        self,
        filesystem_policy: FilesystemPolicy | None = None,
        target_policy: TargetPolicy | None = None,
    ) -> None:
        self.filesystem_policy = filesystem_policy or FilesystemPolicy()
        self.target_policy = target_policy or TargetPolicy()
        self.command_policy = CommandPolicy(self.filesystem_policy)
        self.web_request_policy = WebRequestPolicy(self.target_policy)

    def evaluate(
        self,
        tool_call: ToolCall,
        metadata: ToolMetadata,
        context: ExecutionContext,
    ) -> PolicyDecision:
        try:
            mode = ExecutionMode(context.execution_mode)
        except ValueError:
            return PolicyDecision(
                PolicyDecisionType.DENY,
                "unknown execution mode",
                ToolRiskLevel.HIGH,
            )

        filesystem_decision = self.filesystem_policy.evaluate(
            tool_call,
            metadata,
            context,
        )
        if filesystem_decision is not None:
            return filesystem_decision

        if (
            mode is ExecutionMode.AUTONOMOUS_LOCAL
            and not metadata.autonomous_allowed
        ):
            return PolicyDecision(
                PolicyDecisionType.DENY,
                f"tool is not permitted in autonomous_local mode: {metadata.name}",
                ToolRiskLevel.HIGH,
            )

        if metadata.name == "bash":
            command = tool_call.arguments.get("command", "")
            return self.command_policy.evaluate(str(command), context)

        if metadata.name == "http_request":
            return self.web_request_policy.evaluate(tool_call, context)

        if metadata.requires_network:
            return PolicyDecision(
                PolicyDecisionType.REQUIRE_APPROVAL,
                "network-capable tool requires approval",
                ToolRiskLevel.MEDIUM,
            )
        if (
            mode is ExecutionMode.AUTONOMOUS_LOCAL
            and metadata.autonomous_allowed
            and metadata.risk_level is not ToolRiskLevel.HIGH
        ):
            return PolicyDecision(
                PolicyDecisionType.ALLOW,
                "explicitly autonomous workspace-scoped tool",
                metadata.risk_level,
            )
        if metadata.writes_files:
            return PolicyDecision(
                PolicyDecisionType.REQUIRE_APPROVAL,
                "file-writing tool requires approval",
                ToolRiskLevel.MEDIUM,
            )
        if metadata.risk_level is ToolRiskLevel.LOW:
            return PolicyDecision(
                PolicyDecisionType.ALLOW,
                "registered read-only low-risk tool",
                ToolRiskLevel.LOW,
            )
        return PolicyDecision(
            PolicyDecisionType.REQUIRE_APPROVAL,
            "default-safe policy requires approval",
            metadata.risk_level,
        )
