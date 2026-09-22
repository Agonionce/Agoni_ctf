"""Read-only R3 skill discovery and routing commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from agent.domains.loader import SkillLoader
from agent.domains.router import SkillRouter
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from config import Config

app = typer.Typer(help="R3 Skill knowledge catalog")


def _load_public_settings() -> tuple[list[str], str, str]:
    """Load paths/routing settings without exposing configuration values."""

    try:
        config = Config.load_config()
    except ValueError:
        config = {}
    skill_config = config.get("skills")
    skill_paths = skill_config.get("paths", []) if isinstance(skill_config, dict) else []
    if not isinstance(skill_paths, list):
        skill_paths = []
    domain_config = config.get("domain")
    default_domain = (
        domain_config.get("default", "auto")
        if isinstance(domain_config, dict)
        else "auto"
    )
    checkpoint_dir = config.get("checkpoint_dir", "./checkpoints")
    if not isinstance(checkpoint_dir, str):
        checkpoint_dir = "./checkpoints"
    return skill_paths, str(default_domain), checkpoint_dir


def _get_loader() -> SkillLoader:
    skill_paths, _, _ = _load_public_settings()
    return SkillLoader(extra_paths=skill_paths)


@app.command("list")
def list_command() -> None:
    """列出所有可用 skill。"""
    console = Console()
    skills = _get_loader().all()

    if not skills:
        console.print("[yellow]未找到任何 skill[/yellow]")
        console.print(
            "请在 skills/ 目录下创建带 R3 metadata 的 Markdown 文件，"
            "或在 config.json 中配置 skills.paths"
        )
        return

    table = Table(title="Available Skills")
    table.add_column("Domain", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Priority")
    table.add_column("Description", style="white")

    for skill in skills:
        table.add_row(
            skill.domain,
            skill.name,
            skill.priority.value,
            skill.description,
        )

    console.print(table)


@app.command("show")
def show_command(
    name: str = typer.Argument(help="Skill 名称"),
) -> None:
    """查看指定 skill 的详细内容。"""
    loader = _get_loader()
    try:
        skill = loader.get(name)
    except KeyError:
        typer.echo(f"未找到 skill: {name}")
        available = [item.name for item in loader.all()]
        if available:
            typer.echo(f"可用 skill: {', '.join(available)}")
        raise typer.Exit(1)

    typer.echo(f"Skill: {skill.name}")
    typer.echo(f"Domain: {skill.domain}")
    typer.echo(f"Priority: {skill.priority.value}")
    typer.echo(f"Description: {skill.description}")
    typer.echo("Knowledge:")
    for item in skill.knowledge:
        typer.echo(f"- {item}")
    typer.echo("Strategies:")
    for item in skill.strategies:
        typer.echo(f"- {item}")
    typer.echo("Heuristics:")
    for item in skill.heuristics:
        typer.echo(f"- {item}")


@app.command("current")
def current_command() -> None:
    """Show deterministic R3 routing for the latest local checkpoint."""

    skill_paths, default_domain, checkpoint_dir = _load_public_settings()
    checkpoint = IntelligenceCheckpoint.latest(checkpoint_dir)
    if checkpoint is None:
        typer.echo("尚无活动 checkpoint，无法确定当前 challenge skill")
        return
    data = checkpoint.load()
    loader = SkillLoader(extra_paths=skill_paths)
    selection = SkillRouter(
        loader=loader,
        default_domain=default_domain,
    ).route(data.run_state.challenge, data.artifacts)
    typer.echo(f"Domains: {', '.join(selection.selected_domains)}")
    typer.echo(f"Skills: {', '.join(selection.selected_skills)}")
    typer.echo(f"Confidence: {selection.confidence:.3f}")
    typer.echo(f"Rationale: {'; '.join(selection.rationale)}")
