"""Configuration registry and health projection for configured MCP servers."""

from __future__ import annotations

from typing import Any, Mapping

from agent.mcp.models import (
    MCPServerConfig,
    MCPServerHealth,
    MCPServerStatus,
    redact_mcp_status_value,
)


class MCPServerRegistry:
    """Own explicit server declarations; it does not create a client by itself."""

    def __init__(self, servers: list[MCPServerConfig] = ()) -> None:
        self._servers: dict[str, MCPServerConfig] = {}
        self._status: dict[str, MCPServerStatus] = {}
        for server in servers:
            if server.server_id in self._servers:
                raise ValueError(f"duplicate MCP server id: {server.server_id}")
            self._servers[server.server_id] = server
            self._status[server.server_id] = MCPServerStatus(
                server_id=server.server_id,
                health=(MCPServerHealth.UNKNOWN if server.enabled else MCPServerHealth.DISABLED),
                message=("configured" if server.enabled else "disabled by configuration"),
            )

    @classmethod
    def from_config(cls, data: Mapping[str, Any] | None) -> "MCPServerRegistry":
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise ValueError("mcp configuration must be an object")
        unknown = sorted(set(data) - {"servers"})
        if unknown:
            raise ValueError(f"unknown mcp configuration fields: {', '.join(unknown)}")
        raw_servers = data.get("servers", [])
        if not isinstance(raw_servers, list):
            raise ValueError("mcp.servers must be an array")
        return cls([MCPServerConfig.from_mapping(item) for item in raw_servers])

    def get(self, server_id: str) -> MCPServerConfig | None:
        return self._servers.get(server_id)

    def enabled(self) -> list[MCPServerConfig]:
        return [item for item in self.list() if item.enabled]

    def list(self) -> list[MCPServerConfig]:
        return [self._servers[name] for name in sorted(self._servers)]

    def status(self, server_id: str) -> MCPServerStatus | None:
        return self._status.get(server_id)

    def statuses(self) -> list[MCPServerStatus]:
        return [self._status[name] for name in sorted(self._status)]

    def mark_ready(
        self,
        server_id: str,
        *,
        server_name: str,
        server_version: str,
        tools: list[Any],
    ) -> None:
        status = self._require_status(server_id)
        status.health = MCPServerHealth.READY
        status.message = "local MCP handshake and tool discovery succeeded"
        status.server_name = server_name
        status.server_version = server_version
        status.tools = list(tools)

    def mark_error(self, server_id: str, message: str) -> None:
        status = self._require_status(server_id)
        status.health = MCPServerHealth.ERROR
        status.message = str(redact_mcp_status_value(message))[:1000]

    def record_call(self, server_id: str, payload: Mapping[str, Any]) -> None:
        status = self._require_status(server_id)
        value = redact_mcp_status_value(dict(payload))
        status.last_call = value if isinstance(value, dict) else {}

    def _require_status(self, server_id: str) -> MCPServerStatus:
        try:
            return self._status[server_id]
        except KeyError as error:
            raise ValueError(f"unknown MCP server: {server_id}") from error
