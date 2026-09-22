"""R14 MCP Foundation: external capabilities adapted into ToolRuntime."""

from agent.mcp.adapter import MCPToolAdapter, MCPToolAdapterRegistry
from agent.mcp.client import MCPClientManager, MCPError
from agent.mcp.models import (
    MCPCapabilityProfile,
    MCPServerConfig,
    MCPServerHealth,
    MCPToolDescriptor,
)
from agent.mcp.registry import MCPServerRegistry

__all__ = [
    "MCPCapabilityProfile",
    "MCPClientManager",
    "MCPError",
    "MCPServerConfig",
    "MCPServerHealth",
    "MCPServerRegistry",
    "MCPToolAdapter",
    "MCPToolAdapterRegistry",
    "MCPToolDescriptor",
]
