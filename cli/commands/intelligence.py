"""Read-only inspection of the latest R2 intelligence checkpoint."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agent.intelligence.checkpoint import IntelligenceCheckpoint
from config import Config

app = typer.Typer(help="R2 CTF Intelligence 状态")


@app.command("show")
def show_command(
    checkpoint: Path | None = typer.Option(
        None,
        "--checkpoint",
        help="R2 checkpoint 目录；默认使用最新 checkpoint",
    ),
) -> None:
    """Show state counts and masked credentials without executing a Tool."""

    if checkpoint is None:
        config = Config.load_config()
        checkpoint_dir = config.get("checkpoint_dir", "./checkpoints")
        root = checkpoint_dir if isinstance(checkpoint_dir, str) else "./checkpoints"
        checkpoint_store = IntelligenceCheckpoint.latest(root)
    else:
        checkpoint_store = IntelligenceCheckpoint(checkpoint)
    console = Console()
    if checkpoint_store is None:
        console.print("[yellow]未找到 R2 Intelligence checkpoint[/yellow]")
        return
    data = checkpoint_store.load()
    state = data.intelligence_store.state
    table = Table(title="CTF Intelligence State")
    table.add_column("Collection", style="cyan")
    table.add_column("Count", style="green")
    table.add_row("Facts", str(len(state.facts)))
    table.add_row("Hypotheses", str(len(state.hypotheses)))
    table.add_row("Failed Attempts", str(len(state.failed_attempts)))
    table.add_row("Findings", str(len(state.findings)))
    table.add_row("Credentials", str(len(state.credentials)))
    table.add_row("Attack Surface", str(len(state.attack_surface)))
    table.add_row("Open Questions", str(len(state.open_questions)))
    table.add_row("Experiments", str(len(state.experiments)))
    table.add_row("Evidence", str(len(state.evidence)))
    table.add_row("Artifacts", str(len(data.artifacts)))
    console.print(table)
    if state.credentials:
        console.print("Credentials (masked):")
        for credential in state.credentials:
            console.print(f"- {credential.credential_type}: {credential.masked_value()} ({credential.status.value})")
