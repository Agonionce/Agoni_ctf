"""Read-only environment checks for the R9.2 Sandbox Layer."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from agent.sandbox.docker import DockerBackend


DEFAULT_SANDBOX_IMAGE = "python:3.12-alpine"

app = typer.Typer(help="本地 Docker Sandbox 状态")


@app.command("check")
def check_command() -> None:
    """Check the Docker client, daemon, and local default image without pulling."""

    backend = DockerBackend()
    availability = backend.check()
    image_available = (
        backend.image_available(DEFAULT_SANDBOX_IMAGE)
        if availability.available
        else False
    )
    table = Table(title="Sandbox Runtime Check")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Detail", style="white")
    table.add_row(
        "Docker CLI",
        "PASS" if availability.client_available else "FAIL",
        availability.version or availability.error or "not available",
    )
    table.add_row(
        "Docker daemon",
        "PASS" if availability.daemon_available else "FAIL",
        "network-disabled sandbox backend"
        if availability.daemon_available
        else availability.error or "not available",
    )
    table.add_row(
        "Local image",
        "PASS" if image_available else "FAIL",
        DEFAULT_SANDBOX_IMAGE + " (no automatic pull)",
    )
    Console().print(table)
    if not availability.available or not image_available:
        raise typer.Exit(code=1)
