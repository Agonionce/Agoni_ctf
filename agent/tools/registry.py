"""Registry for R1 Tool implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from agent.sandbox.manager import SandboxManager
from agent.tools.builtin import BashTool, FileInfoTool, PythonExecutionTool
from agent.tools.contracts import Tool
from agent.tools.http_request import HTTPRequestTool
from agent.tools.sandbox_python import SandboxPythonTool
from agent.tools.validation import ToolArgumentValidator
from agent.tools.web_intelligence import WebIntelligenceTool
from agent.tools.workspace import (
    ArchiveListTool,
    FileHashTool,
    WorkspaceListTool,
    WorkspaceReadBytesTool,
    WorkspaceReadTextTool,
    WorkspaceWriteTextTool,
)

if TYPE_CHECKING:
    from agent.mcp.client import MCPClientManager


class ToolRegistry:
    """Own available Tool instances and expose Planner-safe schemas."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.metadata.name
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        ToolArgumentValidator.check_schema(tool.input_schema)
        self._tools[name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list(self) -> List[Tool]:
        return [self._tools[name] for name in sorted(self._tools)]

    def schemas(self) -> List[dict]:
        return [tool.schema() for tool in self.list()]


def build_default_registry(
    sandbox_manager: SandboxManager | None = None,
    mcp_manager: "MCPClientManager | None" = None,
) -> ToolRegistry:
    """Build the intentionally small R1 Tool surface."""

    registry = ToolRegistry()
    registry.register(FileInfoTool())
    registry.register(HTTPRequestTool())
    registry.register(WebIntelligenceTool())
    registry.register(WorkspaceListTool())
    registry.register(WorkspaceReadTextTool())
    registry.register(WorkspaceReadBytesTool())
    registry.register(WorkspaceWriteTextTool())
    registry.register(FileHashTool())
    registry.register(ArchiveListTool())
    registry.register(SandboxPythonTool(sandbox_manager or SandboxManager()))
    registry.register(PythonExecutionTool())
    registry.register(BashTool())
    if mcp_manager is not None:
        # Discovery returns external schemas, but every invocation still enters
        # this same registry and subsequently ToolRuntime / Policy / Approval.
        from agent.mcp.adapter import MCPToolAdapterRegistry

        MCPToolAdapterRegistry(mcp_manager).register_discovered(registry)
    return registry
