"""Read-only R1 execution-policy inspection command."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from agent.tools.settings import ExecutionSettings
from config import Config

app = typer.Typer(help="R1 执行策略检查")


@app.command("check")
def check_command() -> None:
    """Show non-secret R1 execution defaults without running a Tool."""

    try:
        config = Config.load_config()
        settings = ExecutionSettings.from_mapping(config.get("execution"))
    except (ValueError, OSError) as error:
        raise typer.BadParameter(str(error)) from error

    table = Table(title="R1 Execution Policy")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("mode", settings.mode)
    table.add_row("workspace_root", settings.workspace_root)
    table.add_row("default_policy", settings.default_policy)
    table.add_row("unknown action", "REQUIRE_APPROVAL")
    table.add_row("network runtime", "not implemented")
    Console().print(table)
