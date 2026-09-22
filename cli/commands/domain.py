"""Read-only R3 domain catalog commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from agent.domains.registry import build_default_domain_registry

app = typer.Typer(help="R3 Domain Intelligence catalog")


@app.command("list")
def list_command() -> None:
    """List deterministic challenge domains; performs no execution."""

    table = Table(title="Available Domains")
    table.add_column("Domain", style="cyan")
    table.add_column("Description")
    table.add_column("Skills", style="dim")
    for domain in build_default_domain_registry().all():
        table.add_row(domain.name, domain.description, ", ".join(domain.skill_names))
    Console().print(table)
