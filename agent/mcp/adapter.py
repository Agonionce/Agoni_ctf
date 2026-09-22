"""Adapt discovered MCP tools to Agonionce's existing first-class Tool API."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Mapping

from agent.mcp.client import MCPCallResponse, MCPClientManager, MCPError
from agent.mcp.models import MCPCapabilityProfile, MCPToolDescriptor
from agent.mcp.models import redact_mcp_status_value
from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
)
from agent.tools.registry import ToolRegistry


class MCPToolAdapter(Tool):
    """One discovered remote MCP capability expressed as a normal Tool."""

    MAX_STDOUT_PREVIEW = 4096
    MAX_ARTIFACT_BYTES = 2_000_000

    def __init__(
        self,
        manager: MCPClientManager,
        descriptor: MCPToolDescriptor,
        capability: MCPCapabilityProfile,
    ) -> None:
        self.manager = manager
        self.descriptor = descriptor
        self.capability = capability
        self.metadata = ToolMetadata(
            name=self.tool_name(descriptor.server_id, descriptor.name),
            description=(
                f"MCP capability from configured local server {descriptor.server_id}: "
                f"{descriptor.description}"
            ),
            risk_level=capability.risk_level,
            requires_network=capability.network,
            writes_files=(
                capability.state_changing
                or capability.filesystem
                or capability.execution
                or capability.external_application
            ),
            execution_type="mcp_stdio",
            autonomous_allowed=(
                capability.autonomous_allowed
                and capability.read_only
                and not capability.has_side_effects
            ),
            provenance={
                "kind": "mcp",
                "server": descriptor.server_id,
                "remote_tool": descriptor.name,
            },
        )
        self.input_schema = dict(descriptor.input_schema)

    @staticmethod
    def tool_name(server_id: str, remote_tool_name: str) -> str:
        normalized_server = re.sub(r"[^A-Za-z0-9_]", "_", server_id)
        normalized_tool = re.sub(r"[^A-Za-z0-9_]", "_", remote_tool_name)
        return f"mcp__{normalized_server}__{normalized_tool}"

    def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        try:
            response = self.manager.call_tool(
                self.descriptor.server_id,
                self.descriptor.name,
                arguments,
            )
        except MCPError as error:
            return self._error_output(context, str(redact_mcp_status_value(str(error))))
        return self._normalize_response(context, response)

    def _normalize_response(
        self,
        context: ExecutionContext,
        response: MCPCallResponse,
    ) -> ToolExecutionOutput:
        result = response.result
        content = result.get("content", [])
        content_items = content if isinstance(content, list) else []
        text_items = [
            str(item.get("text", ""))
            for item in content_items
            if isinstance(item, Mapping) and item.get("type") == "text"
        ]
        combined = "\n".join(item for item in text_items if item)
        is_error = bool(result.get("isError", False))
        full_payload = {
            "schema_version": "r14-mcp-result-v1",
            "provenance": self._provenance(response),
            "success": not is_error,
            "result": result,
        }
        try:
            artifact_path = self._write_artifact(context, full_payload)
        except ValueError as error:
            return self._error_output(context, str(error))
        summary = {
            "server": self.descriptor.server_id,
            "remote_tool": self.descriptor.name,
            "success": not is_error,
            "content_items": len(content_items),
            "text_preview": combined[: self.MAX_STDOUT_PREVIEW],
            "truncated": len(combined) > self.MAX_STDOUT_PREVIEW,
        }
        error = "MCP tool reported an error" if is_error else None
        return ToolExecutionOutput(
            success=not is_error,
            stdout=json.dumps(summary, ensure_ascii=False),
            error=error,
            exit_code=0 if not is_error else 1,
            artifact_paths=[artifact_path],
            artifact_type="mcp_result",
            metadata={
                "mcp": {
                    **self._provenance(response),
                    "result_is_error": is_error,
                    "content_items": len(content_items),
                    "artifact_path": str(artifact_path.relative_to(context.workspace_root)),
                },
            },
        )

    def _error_output(self, context: ExecutionContext, error: str) -> ToolExecutionOutput:
        error = error[:4096]
        payload = {
            "schema_version": "r14-mcp-result-v1",
            "provenance": self._provenance(),
            "success": False,
            "error": error,
        }
        artifact_path = self._write_artifact(context, payload)
        return ToolExecutionOutput(
            success=False,
            error=error,
            exit_code=1,
            artifact_paths=[artifact_path],
            artifact_type="mcp_result",
            metadata={
                "mcp": {
                    **self._provenance(),
                    "result_is_error": True,
                    "artifact_path": str(artifact_path.relative_to(context.workspace_root)),
                },
            },
        )

    def _provenance(self, response: MCPCallResponse | None = None) -> dict[str, Any]:
        schema_json = json.dumps(self.input_schema, ensure_ascii=False, sort_keys=True)
        return {
            "server": self.descriptor.server_id,
            "transport": "stdio",
            "remote_tool": self.descriptor.name,
            "server_name": response.server_name if response is not None else "",
            "server_version": response.server_version if response is not None else "",
            "schema_sha256": hashlib.sha256(schema_json.encode("utf-8")).hexdigest(),
            "capability": self.capability.to_dict(),
        }

    def _write_artifact(self, context: ExecutionContext, payload: Mapping[str, Any]) -> Path:
        directory = context.output_dir / "mcp"
        directory.mkdir(parents=True, exist_ok=True)
        safe_server = re.sub(r"[^A-Za-z0-9_.-]", "_", self.descriptor.server_id)
        safe_tool = re.sub(r"[^A-Za-z0-9_.-]", "_", self.descriptor.name)
        path = directory / (
            f"{safe_server}-{safe_tool}-step-{context.step_id:04d}-{uuid.uuid4().hex[:12]}.json"
        )
        encoded = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(encoded.encode("utf-8")) > self.MAX_ARTIFACT_BYTES:
            raise ValueError("MCP result exceeds the R14 2 MB artifact limit")
        path.write_text(encoded, encoding="utf-8")
        return path


class MCPToolAdapterRegistry:
    """Discover enabled MCP tools and register only validated Tool adapters."""

    def __init__(self, manager: MCPClientManager) -> None:
        self.manager = manager
        self.discovery_errors: dict[str, str] = {}

    def register_discovered(self, registry: ToolRegistry) -> list[MCPToolAdapter]:
        adapters: list[MCPToolAdapter] = []
        for server_id, descriptors in self.manager.discover_enabled().items():
            config = self.manager.registry.get(server_id)
            if config is None:
                continue
            for descriptor in descriptors:
                adapter = MCPToolAdapter(
                    self.manager,
                    descriptor,
                    config.capability_for(descriptor.name),
                )
                try:
                    registry.register(adapter)
                except ValueError as error:
                    # A malformed remote schema is isolated to that configured
                    # server.  It is never exposed to Planner, while built-in
                    # and other valid MCP tools remain available.
                    message = f"MCP tool {descriptor.name} was not registered: {error}"
                    self.manager.registry.mark_error(server_id, message)
                    self.discovery_errors[server_id] = message
                    continue
                adapters.append(adapter)
        for status in self.manager.registry.statuses():
            if status.health.value == "ERROR":
                self.discovery_errors[status.server_id] = status.message
        return adapters
