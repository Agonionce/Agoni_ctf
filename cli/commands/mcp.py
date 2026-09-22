"""Read-only inspection commands for explicitly configured local MCP servers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from agent.mcp.client import MCPClientManager, MCPError
from agent.mcp.registry import MCPServerRegistry
from config import Config


app = typer.Typer(help="R14 MCP 本地服务器与工具状态")


def _registry(config_path: Path | None) -> MCPServerRegistry:
    config = Config.load_config(str(config_path) if config_path is not None else "./config.json")
    raw_mcp = config.get("mcp")
    return MCPServerRegistry.from_config(raw_mcp if isinstance(raw_mcp, dict) else None)


def _refresh(manager: MCPClientManager, server_id: str | None = None) -> None:
    servers = (
        [manager.registry.get(server_id)]
        if server_id is not None
        else manager.registry.enabled()
    )
    for server in servers:
        if server is None:
            raise typer.BadParameter(f"未知 MCP server: {server_id}")
        if not server.enabled:
            continue
        try:
            manager.discover(server.server_id)
        except MCPError:
            # Registry retains a bounded health error for rendering below.
            continue


@app.command("list")
def list_command(
    config_path: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """List configured MCP servers without starting them."""

    registry = _registry(config_path)
    table = Table(title="Configured MCP Servers")
    table.add_column("Server", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Transport", style="magenta")
    table.add_column("Health", style="yellow")
    table.add_column("Declared tools", style="white")
    for server in registry.list():
        status = registry.status(server.server_id)
        table.add_row(
            server.server_id,
            "yes" if server.enabled else "no",
            server.transport.value,
            status.health.value if status is not None else "UNKNOWN",
            str(len(server.tool_capabilities)),
        )
    Console().print(table)


@app.command("status")
def status_command(
    config_path: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """Perform local MCP handshake and discovery, then render health."""

    registry = _registry(config_path)
    manager = MCPClientManager(registry)
    _refresh(manager)
    table = Table(title="MCP Server Health")
    table.add_column("Server", style="cyan")
    table.add_column("Health", style="yellow")
    table.add_column("Tools", style="green")
    table.add_column("Server version", style="white")
    table.add_column("Detail", style="white")
    for status in registry.statuses():
        table.add_row(
            status.server_id,
            status.health.value,
            str(len(status.tools)),
            " ".join(item for item in (status.server_name, status.server_version) if item) or "-",
            status.message or "-",
        )
    Console().print(table)


@app.command("tools")
def tools_command(
    server: str | None = typer.Argument(None, help="可选的 MCP server id"),
    config_path: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """Discover and list MCP tool schemas; this does not call an MCP tool."""

    registry = _registry(config_path)
    manager = MCPClientManager(registry)
    _refresh(manager, server)
    table = Table(title="Discovered MCP Tools")
    table.add_column("Server", style="cyan")
    table.add_column("Tool", style="green")
    table.add_column("Parameters", style="magenta")
    table.add_column("Description", style="white")
    for status in registry.statuses():
        if server is not None and status.server_id != server:
            continue
        for tool in status.tools:
            properties = tool.input_schema.get("properties", {})
            names = ", ".join(sorted(properties)) if isinstance(properties, dict) else "-"
            table.add_row(status.server_id, tool.name, names or "-", tool.description)
    Console().print(table)


@app.command("inspect")
def inspect_command(
    server: str = typer.Argument(..., help="MCP server id"),
    config_path: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """Show one server's safe config, health, provenance, and full tool schemas."""

    registry = _registry(config_path)
    config = registry.get(server)
    if config is None:
        raise typer.BadParameter(f"未知 MCP server: {server}")
    manager = MCPClientManager(registry)
    _refresh(manager, server)
    status = registry.status(server)
    payload: dict[str, Any] = {
        "config": config.safe_dict(),
        "status": status.safe_dict() if status is not None else {},
    }
    Console().print_json(data=payload)
