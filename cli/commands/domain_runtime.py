"""Read-only R4 Domain Runtime catalog and state commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from agent.domains.loader import SkillLoader
from agent.domains.manager import build_default_runtime_manager
from agent.domains.router import SkillRouter
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from config import Config

app = typer.Typer(help="R4 Domain Runtime lifecycle inspection")


def _settings() -> tuple[str, list[str], str]:
    try:
        config = Config.load_config()
    except ValueError:
        config = {}
    checkpoint_dir = config.get("checkpoint_dir", "./checkpoints")
    if not isinstance(checkpoint_dir, str):
        checkpoint_dir = "./checkpoints"
    skills_config = config.get("skills")
    paths = skills_config.get("paths", []) if isinstance(skills_config, dict) else []
    if not isinstance(paths, list):
        paths = []
    domain_config = config.get("domain")
    default_domain = (
        domain_config.get("default", "auto")
        if isinstance(domain_config, dict)
        else "auto"
    )
    return checkpoint_dir, paths, str(default_domain)


@app.command("list")
def list_command() -> None:
    """List registered declarative runtimes and their phases."""

    table = Table(title="Available Domain Runtimes")
    table.add_column("Runtime", style="cyan")
    table.add_column("Initial Phase", style="green")
    table.add_column("Lifecycle")
    for runtime in build_default_runtime_manager().list():
        phases = runtime.phases()
        table.add_row(
            runtime.name,
            phases[0].name,
            " → ".join(phase.name for phase in phases),
        )
    Console().print(table)


@app.command("current")
def current_command() -> None:
    """Show persisted R4 state, or infer initial state for an older checkpoint."""

    checkpoint_dir, skill_paths, default_domain = _settings()
    checkpoint = IntelligenceCheckpoint.latest(checkpoint_dir)
    if checkpoint is None:
        typer.echo("尚无活动 checkpoint，无法确定当前 Domain Runtime")
        return
    data = checkpoint.load()
    manager = build_default_runtime_manager()
    if data.domain_runtime_state is not None:
        state = manager.initialize(
            data.domain_runtime_state.domain,
            data.run_state.challenge,
            data.domain_runtime_state,
        )
        source = "checkpoint"
    else:
        loader = SkillLoader(extra_paths=skill_paths)
        selection = SkillRouter(
            loader=loader,
            default_domain=default_domain,
        ).route(data.run_state.challenge, data.artifacts)
        state = manager.initialize(selection.primary_domain, data.run_state.challenge)
        source = "inferred (not persisted in legacy checkpoint)"
    current = manager.generate_context()["phase"]
    typer.echo(f"Runtime: {state.domain}")
    typer.echo(f"Phase: {state.phase}")
    typer.echo(f"Goal: {current['goal']}")
    typer.echo(f"History: {' → '.join(state.phase_history)}")
    typer.echo(f"Source: {source}")
