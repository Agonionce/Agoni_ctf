"""Minimal local stdio MCP client with bounded request and lifecycle handling."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

from agent.mcp.models import MCPServerConfig, MCPToolDescriptor
from agent.mcp.registry import MCPServerRegistry


class MCPError(RuntimeError):
    """Normalized MCP transport, protocol, or remote-tool failure."""


@dataclass(frozen=True)
class MCPCallResponse:
    server_id: str
    tool_name: str
    result: dict[str, Any]
    server_name: str = ""
    server_version: str = ""


class StdioMCPClient:
    """One short-lived MCP stdio session using newline-delimited JSON-RPC.

    The client intentionally implements only the foundation methods needed for
    local discovery and invocation: initialize, tools/list, and tools/call.
    No shell is used to start a configured server, and no remote transport is
    accepted in R14.
    """

    PROTOCOL_VERSION = "2024-11-05"
    MAX_MESSAGE_BYTES = 2_000_000

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[dict[str, Any] | BaseException] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._next_id = 0
        self._lock = threading.RLock()
        self.server_name = ""
        self.server_version = ""

    def __enter__(self) -> "StdioMCPClient":
        self.connect()
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        self.close()

    def connect(self) -> None:
        with self._lock:
            if self._process is not None:
                return
            try:
                self._process = subprocess.Popen(
                    [self.config.command, *self.config.args],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
            except OSError as error:
                raise MCPError(f"could not start local MCP server {self.config.server_id}: {error}") from error
            if self._process.stdin is None or self._process.stdout is None:
                self.close()
                raise MCPError("local MCP server has no usable stdio streams")
            self._reader = threading.Thread(
                target=self._read_messages,
                name=f"mcp-{self.config.server_id}-reader",
                daemon=True,
            )
            self._reader.start()
            result = self._request(
                "initialize",
                {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "Agonionce", "version": "R14"},
                },
            )
            server_info = result.get("serverInfo", {})
            if isinstance(server_info, Mapping):
                self.server_name = str(server_info.get("name", ""))
                self.server_version = str(server_info.get("version", ""))
            self._notify("notifications/initialized", {})

    def list_tools(self) -> list[MCPToolDescriptor]:
        result = self._request("tools/list", {})
        raw_tools = result.get("tools", [])
        if not isinstance(raw_tools, list):
            raise MCPError("MCP tools/list result must contain a tools array")
        try:
            return [
                MCPToolDescriptor.from_mapping(self.config.server_id, item)
                for item in raw_tools
                if isinstance(item, Mapping)
            ]
        except ValueError as error:
            raise MCPError(str(error)) from error

    def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> MCPCallResponse:
        result = self._request(
            "tools/call",
            {"name": tool_name, "arguments": dict(arguments)},
        )
        return MCPCallResponse(
            server_id=self.config.server_id,
            tool_name=tool_name,
            result=result,
            server_name=self.server_name,
            server_version=self.server_version,
        )

    def close(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            if process is None:
                return
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.5)

    def _request(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._ensure_running()
            self._next_id += 1
            request_id = self._next_id
            self._send({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": dict(params),
            })
            deadline = time.monotonic() + self.config.timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MCPError(
                        f"MCP {method} timed out after {self.config.timeout_seconds:g}s"
                    )
                try:
                    message = self._messages.get(timeout=remaining)
                except queue.Empty as error:
                    raise MCPError(
                        f"MCP {method} timed out after {self.config.timeout_seconds:g}s"
                    ) from error
                if isinstance(message, BaseException):
                    raise MCPError(str(message)) from message
                if message.get("id") != request_id:
                    # Notifications are expected and are not a response to the
                    # current request.  R14 performs calls serially, so any
                    # other response is protocol-invalid rather than reusable.
                    if "id" in message:
                        raise MCPError("received an unexpected MCP response id")
                    continue
                error_payload = message.get("error")
                if isinstance(error_payload, Mapping):
                    raise MCPError(
                        f"MCP {method} failed: {error_payload.get('message', 'remote error')}"
                    )
                result = message.get("result")
                if not isinstance(result, Mapping):
                    raise MCPError(f"MCP {method} response has no object result")
                return dict(result)

    def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    def _send(self, payload: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise MCPError("MCP client is not connected")
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except OSError as error:
            raise MCPError(f"could not write to MCP server: {error}") from error

    def _ensure_running(self) -> None:
        if self._process is None:
            raise MCPError("MCP client is not connected")
        return_code = self._process.poll()
        if return_code is not None:
            raise MCPError(f"MCP server exited with code {return_code}")

    def _read_messages(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while True:
                line = process.stdout.readline(self.MAX_MESSAGE_BYTES + 1)
                if not line:
                    break
                if len(line.encode("utf-8")) > self.MAX_MESSAGE_BYTES:
                    self._messages.put(MCPError(
                        "MCP server response exceeds the R14 2 MB message limit"
                    ))
                    break
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as error:
                    self._messages.put(MCPError(f"invalid JSON from MCP server: {error}"))
                    continue
                if not isinstance(payload, dict):
                    self._messages.put(MCPError("MCP server emitted a non-object message"))
                    continue
                self._messages.put(payload)
        except OSError as error:
            self._messages.put(MCPError(f"MCP stdio read failed: {error}"))
        finally:
            if process.poll() is not None:
                self._messages.put(MCPError(f"MCP server exited with code {process.returncode}"))


class MCPClientManager:
    """Coordinate short-lived local MCP sessions and durable status projections."""

    def __init__(self, registry: MCPServerRegistry) -> None:
        self.registry = registry

    def discover(self, server_id: str) -> list[MCPToolDescriptor]:
        config = self._enabled_config(server_id)
        try:
            with StdioMCPClient(config) as client:
                tools = client.list_tools()
                self.registry.mark_ready(
                    server_id,
                    server_name=client.server_name,
                    server_version=client.server_version,
                    tools=tools,
                )
                return tools
        except MCPError as error:
            self.registry.mark_error(server_id, str(error))
            raise

    def discover_enabled(self) -> dict[str, list[MCPToolDescriptor]]:
        discovered: dict[str, list[MCPToolDescriptor]] = {}
        for config in self.registry.enabled():
            try:
                discovered[config.server_id] = self.discover(config.server_id)
            except MCPError:
                # A failed configured server must not make unrelated built-in
                # capabilities disappear.  Its ERROR health remains visible.
                continue
        return discovered

    def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> MCPCallResponse:
        config = self._enabled_config(server_id)
        started = time.monotonic()
        try:
            with StdioMCPClient(config) as client:
                response = client.call_tool(tool_name, arguments)
                self.registry.record_call(server_id, {
                    "tool": tool_name,
                    "success": not bool(response.result.get("isError", False)),
                    "duration": max(0.0, time.monotonic() - started),
                })
                return response
        except MCPError as error:
            self.registry.mark_error(server_id, str(error))
            self.registry.record_call(server_id, {
                "tool": tool_name,
                "success": False,
                "duration": max(0.0, time.monotonic() - started),
                "error": str(error),
            })
            raise

    def _enabled_config(self, server_id: str) -> MCPServerConfig:
        config = self.registry.get(server_id)
        if config is None:
            raise MCPError(f"unknown MCP server: {server_id}")
        if not config.enabled:
            raise MCPError(f"MCP server is disabled: {server_id}")
        return config
