"""Inspect the first-class R1 ToolRegistry."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from agent.tools.registry import build_default_registry

app = typer.Typer(help="工具信息")


@app.command("list")
def list_command() -> None:
    """List the small, policy-controlled R1 Tool surface."""

    registry = build_default_registry()
    table = Table(title="Available Tools")
    table.add_column("Tool", style="cyan")
    table.add_column("Risk", style="yellow")
    table.add_column("Network", style="magenta")
    table.add_column("Writes", style="magenta")
    table.add_column("Parameters", style="green")
    table.add_column("Description", style="white")

    for tool in registry.list():
        properties = tool.input_schema.get("properties", {})
        parameters = ", ".join(sorted(properties)) if isinstance(properties, dict) else "-"
        table.add_row(
            tool.metadata.name,
            tool.metadata.risk_level.value,
            "yes" if tool.metadata.requires_network else "no",
            "yes" if tool.metadata.writes_files else "no",
            parameters or "-",
            tool.metadata.description,
        )
    Console().print(table)
