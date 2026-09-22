"""Typed, JSON-safe contracts for the R14 MCP Foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Mapping

from agent.tools.contracts import ToolRiskLevel


def redact_mcp_status_value(value: Any) -> Any:
    """Redact status and CLI diagnostics without modifying result artifacts."""

    if isinstance(value, Mapping):
        return {
            str(name): redact_mcp_status_value(item)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [redact_mcp_status_value(item) for item in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r"(?i)\b(?:flag|ctf)\{[^}\r\n]+\}", "<redacted>", value)
    return re.sub(
        r"(?i)\b(password|passwd|token|cookie|secret|credential|api[_-]?key)"
        r"\s*[:=]\s*([^\s,;]+)",
        r"\1=<redacted>",
        value,
    )


class MCPTransport(str, Enum):
    """Transport types supported by the first local-only foundation."""

    STDIO = "stdio"


class MCPServerHealth(str, Enum):
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"
    READY = "READY"
    ERROR = "ERROR"


@dataclass(frozen=True)
class MCPCapabilityProfile:
    """Locally configured effects for one remote MCP capability.

    Server-provided annotations are useful descriptions, but they never lower
    Agonionce policy.  Only this explicit local configuration can classify a
    remote Tool as read-only.
    """

    read_only: bool = False
    state_changing: bool = True
    network: bool = False
    filesystem: bool = False
    execution: bool = False
    external_application: bool = True
    autonomous_allowed: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "MCPCapabilityProfile":
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise ValueError("MCP tool capability declaration must be an object")
        allowed = {
            "read_only",
            "state_changing",
            "network",
            "filesystem",
            "execution",
            "external_application",
            "autonomous_allowed",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f"unknown MCP capability fields: {', '.join(unknown)}")
        values: dict[str, bool] = {}
        for name in allowed:
            value = data.get(name, getattr(cls(), name))
            if not isinstance(value, bool):
                raise ValueError(f"MCP capability {name} must be boolean")
            values[name] = value
        if values["read_only"] and any(
            values[name]
            for name in ("state_changing", "network", "filesystem", "execution", "external_application")
        ):
            raise ValueError("read_only MCP capability cannot declare side effects")
        if values["autonomous_allowed"] and not values["read_only"]:
            raise ValueError("autonomous_allowed MCP capability must be read_only")
        return cls(**values)

    @property
    def risk_level(self) -> ToolRiskLevel:
        if self.read_only and not self.has_side_effects:
            return ToolRiskLevel.LOW
        if self.execution or self.network or self.external_application:
            return ToolRiskLevel.HIGH
        return ToolRiskLevel.MEDIUM

    @property
    def has_side_effects(self) -> bool:
        return any((
            self.state_changing,
            self.network,
            self.filesystem,
            self.execution,
            self.external_application,
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "read_only": self.read_only,
            "state_changing": self.state_changing,
            "network": self.network,
            "filesystem": self.filesystem,
            "execution": self.execution,
            "external_application": self.external_application,
            "autonomous_allowed": self.autonomous_allowed,
            "risk_level": self.risk_level.value,
        }


@dataclass(frozen=True)
class MCPServerConfig:
    server_id: str
    transport: MCPTransport
    command: str
    args: tuple[str, ...] = ()
    enabled: bool = False
    timeout_seconds: float = 10.0
    tool_capabilities: Mapping[str, MCPCapabilityProfile] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "MCPServerConfig":
        if not isinstance(data, Mapping):
            raise ValueError("MCP server entry must be an object")
        allowed = {
            "id", "transport", "command", "args", "enabled", "timeout_seconds", "tool_capabilities"
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f"unknown MCP server fields: {', '.join(unknown)}")
        server_id = data.get("id")
        if not isinstance(server_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", server_id) is None:
            raise ValueError("MCP server id must contain only letters, digits, underscores, or hyphens")
        try:
            transport = MCPTransport(str(data.get("transport", MCPTransport.STDIO.value)))
        except ValueError as error:
            raise ValueError("R14 supports only stdio MCP transport") from error
        command = data.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("MCP server command must be a non-empty string")
        raw_args = data.get("args", [])
        if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
            raise ValueError("MCP server args must be an array of strings")
        enabled = data.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("MCP server enabled must be boolean")
        timeout = data.get("timeout_seconds", 10.0)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 60.0:
            raise ValueError("MCP server timeout_seconds must be between 0.1 and 60")
        raw_capabilities = data.get("tool_capabilities", {})
        if not isinstance(raw_capabilities, Mapping):
            raise ValueError("MCP server tool_capabilities must be an object")
        capabilities: dict[str, MCPCapabilityProfile] = {}
        for tool_name, declaration in raw_capabilities.items():
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError("MCP tool capability names must be non-empty strings")
            if not isinstance(declaration, Mapping):
                raise ValueError("MCP tool capability declaration must be an object")
            capabilities[tool_name] = MCPCapabilityProfile.from_mapping(declaration)
        return cls(
            server_id=server_id,
            transport=transport,
            command=command,
            args=tuple(raw_args),
            enabled=enabled,
            timeout_seconds=float(timeout),
            tool_capabilities=capabilities,
        )

    def capability_for(self, remote_tool_name: str) -> MCPCapabilityProfile:
        return self.tool_capabilities.get(remote_tool_name, MCPCapabilityProfile())

    def safe_dict(self) -> dict[str, Any]:
        """Configuration projection suitable for CLI output; no environment values exist in R14."""

        return {
            "id": self.server_id,
            "transport": self.transport.value,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "tool_capabilities": {
                name: capability.to_dict()
                for name, capability in sorted(self.tool_capabilities.items())
            },
        }


@dataclass(frozen=True)
class MCPToolDescriptor:
    server_id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, server_id: str, data: Mapping[str, Any]) -> "MCPToolDescriptor":
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("MCP tool discovery entry has no valid name")
        schema = data.get("inputSchema", {"type": "object", "properties": {}})
        if not isinstance(schema, Mapping):
            raise ValueError(f"MCP tool {name} inputSchema must be an object")
        annotations = data.get("annotations", {})
        return cls(
            server_id=server_id,
            name=name,
            description=str(data.get("description", "MCP capability")),
            input_schema=dict(schema),
            annotations=dict(annotations) if isinstance(annotations, Mapping) else {},
        )

    def safe_dict(self) -> dict[str, Any]:
        return {
            "server": self.server_id,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "annotations": self.annotations,
        }


@dataclass
class MCPServerStatus:
    server_id: str
    health: MCPServerHealth
    message: str = ""
    server_name: str = ""
    server_version: str = ""
    tools: list[MCPToolDescriptor] = field(default_factory=list)
    last_call: dict[str, Any] = field(default_factory=dict)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "health": self.health.value,
            "message": str(redact_mcp_status_value(self.message)),
            "server_name": self.server_name,
            "server_version": self.server_version,
            "tool_count": len(self.tools),
            "tools": [tool.safe_dict() for tool in self.tools],
            "last_call": redact_mcp_status_value(self.last_call),
        }
