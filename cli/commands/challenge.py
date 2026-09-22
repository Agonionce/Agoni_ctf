"""R8.5 Challenge Intake CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent.challenge.experience import ChallengeExperienceManager
from agent.challenge.importer import ChallengeImporter
from agent.challenge.validator import ALLOWED_DOMAINS
from agent.completion.collector import CompletionCollector
from agent.completion.experience import (
    ExperienceCandidateExtractor,
    ExperienceCandidateStore,
)
from agent.completion.report import ReportGenerator
from agent.completion.lessons import LessonExtractor
from agent.completion.writeup import WriteupGenerator


app = typer.Typer(help="R8.5 intake and R8.6 challenge completion")


@app.command("create")
def create_challenge(
    name: str | None = typer.Option(None, "--name", help="Challenge name"),
    description: str | None = typer.Option(
        None,
        "--description",
        help="Challenge description",
    ),
    description_file: Path | None = typer.Option(
        None,
        "--description-file",
        help="UTF-8 challenge description file",
    ),
    domain: str | None = typer.Option(None, "--domain", help="Challenge domain"),
    target_url: str | None = typer.Option(None, "--url", help="Authorized target URL"),
    attachments: list[Path] | None = typer.Option(
        None,
        "--attachment",
        help="Attachment path; may be repeated",
    ),
    source_paths: list[Path] | None = typer.Option(
        None,
        "--source",
        help="Source file or directory; may be repeated",
    ),
    authorization_scope: str = typer.Option(
        "authorized_ctf_only",
        "--authorization-scope",
        help="Explicit authorization scope label",
    ),
    workspace_root: Path = typer.Option(
        Path("workspace"),
        "--workspace-root",
        help="Contained workspace root",
    ),
    experience_root: Path = typer.Option(
        Path("experiences/challenges"),
        "--experience-root",
        help="Per-challenge experience root",
    ),
    source_root: Path = typer.Option(
        Path("."),
        "--source-root",
        help="Authorized root for local files accepted by intake",
    ),
) -> None:
    """Interactively create a manifest, workspace, and experience folder."""

    interactive = name is None
    if interactive:
        name = typer.prompt("Challenge name")
        if description_file is None:
            description = typer.prompt("Description")
        domain = typer.prompt("Domain", default="auto")
        target_url = typer.prompt("Target URL", default="") or None
        attachment_text = typer.prompt("Attachment", default="")
        source_text = typer.prompt("Source", default="")
        attachments = _split_paths(attachment_text)
        source_paths = _split_paths(source_text)
    if name is None:
        raise typer.BadParameter("--name is required")
    if description is None and description_file is None:
        raise typer.BadParameter("--description or --description-file is required")
    domain = (domain or "auto").lower()
    if domain not in ALLOWED_DOMAINS:
        raise typer.BadParameter(
            f"--domain must be one of: {', '.join(sorted(ALLOWED_DOMAINS))}"
        )
    try:
        result = ChallengeImporter(
            workspace_root=workspace_root,
            experience_root=experience_root,
            source_root=source_root,
        ).import_challenge(
            name=name,
            description=description,
            description_path=description_file,
            domain=domain,
            target_url=target_url,
            attachments=tuple(attachments or ()),
            source_paths=tuple(source_paths or ()),
            authorization_scope=authorization_scope,
        )
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    Console().print(
        Panel(
            f"ID: {result.manifest.challenge_id}\n"
            f"Workspace: {result.workspace.workspace.root}\n"
            f"Experience: {result.experience.root}",
            title="Challenge created",
            border_style="green",
        )
    )


@app.command("list")
def list_challenges(
    experience_root: Path = typer.Option(
        Path("experiences/challenges"),
        "--experience-root",
        help="Per-challenge experience root",
    ),
) -> None:
    """List imported challenge manifests."""

    manager = ChallengeExperienceManager(experience_root)
    table = Table(title="Imported Challenges")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Domain", style="green")
    table.add_column("Created")
    for manifest in manager.store.list():
        table.add_row(
            manifest.challenge_id,
            manifest.name,
            manifest.domain,
            manifest.created_at,
        )
    Console().print(table)


@app.command("show")
def show_challenge(
    challenge_id: str = typer.Argument(..., help="Challenge manifest ID"),
    workspace_root: Path = typer.Option(
        Path("workspace"),
        "--workspace-root",
        help="Contained workspace root",
    ),
    experience_root: Path = typer.Option(
        Path("experiences/challenges"),
        "--experience-root",
        help="Per-challenge experience root",
    ),
) -> None:
    """Show one imported challenge and its bound locations."""

    manager = ChallengeExperienceManager(experience_root)
    manifest = manager.store.get(challenge_id)
    if manifest is None:
        raise typer.BadParameter(f"unknown challenge ID: {challenge_id}")
    table = Table(title="Challenge Details", show_header=False, expand=True)
    table.add_column("Field", style="cyan")
    table.add_column("Value", overflow="fold")
    table.add_row("ID", manifest.challenge_id)
    table.add_row("Name", manifest.name)
    table.add_row("Domain", manifest.domain)
    table.add_row("Target URL", manifest.target_url or "-")
    table.add_row("Authorization", manifest.authorization_scope)
    table.add_row("Workspace", str((workspace_root / manifest.challenge_id).resolve()))
    table.add_row("Experience", str(manager.paths_for(manifest).root))
    Console().print(table)


@app.command("report")
def generate_report(
    challenge_id: str = typer.Argument(..., help="Completed challenge manifest ID"),
    experience_root: Path = typer.Option(
        Path("experiences/challenges"),
        "--experience-root",
        help="Per-challenge experience root",
    ),
) -> None:
    """Generate report.md from the latest persisted run."""

    try:
        snapshot = CompletionCollector.load_latest(
            challenge_id,
            experience_root=experience_root,
        )
        report = CompletionCollector().collect(
            snapshot.manifest,
            snapshot.run_state,
            snapshot.intelligence_state,
            snapshot.artifacts,
        )
        paths = ChallengeExperienceManager(experience_root).paths_for(snapshot.manifest)
        ReportGenerator().write(report, paths.report_file, manifest=snapshot.manifest)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    Console().print(f"[green]Challenge report generated:[/green] {paths.report_file}")


@app.command("writeup")
def generate_writeup(
    challenge_id: str = typer.Argument(..., help="Completed challenge manifest ID"),
    experience_root: Path = typer.Option(
        Path("experiences/challenges"),
        "--experience-root",
        help="Per-challenge experience root",
    ),
) -> None:
    """Generate an evidence-bound writeup.md draft."""

    try:
        snapshot = CompletionCollector.load_latest(
            challenge_id,
            experience_root=experience_root,
        )
        report = CompletionCollector().collect(
            snapshot.manifest,
            snapshot.run_state,
            snapshot.intelligence_state,
            snapshot.artifacts,
        )
        paths = ChallengeExperienceManager(experience_root).paths_for(snapshot.manifest)
        WriteupGenerator().write(snapshot.manifest, report, paths.writeup_file)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    Console().print(f"[green]Writeup draft generated:[/green] {paths.writeup_file}")


@app.command("extract-experience")
def extract_experience(
    challenge_id: str = typer.Argument(..., help="Completed challenge manifest ID"),
    experience_root: Path = typer.Option(
        Path("experiences/challenges"),
        "--experience-root",
        help="Per-challenge experience root",
    ),
) -> None:
    """Extract sanitized PENDING candidates without merging global memory."""

    try:
        snapshot = CompletionCollector.load_latest(
            challenge_id,
            experience_root=experience_root,
        )
        report = CompletionCollector().collect(
            snapshot.manifest,
            snapshot.run_state,
            snapshot.intelligence_state,
            snapshot.artifacts,
        )
        lessons = ReportGenerator.derive_lessons(report)
        lesson_candidates = LessonExtractor().extract(report)
        candidates = ExperienceCandidateExtractor().extract(
            report,
            report.experiments,
            lessons,
            lesson_candidates,
        )
        paths = ChallengeExperienceManager(experience_root).paths_for(snapshot.manifest)
        LessonExtractor.write(
            paths.lesson_candidates_file,
            snapshot.manifest.challenge_id,
            lesson_candidates,
        )
        stored = ExperienceCandidateStore(
            paths.experience_candidates_file,
            challenge_id=snapshot.manifest.challenge_id,
        ).merge_extracted(candidates)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    Console().print(
        f"[green]Experience candidates extracted:[/green] {len(stored)} "
        f"-> {paths.experience_candidates_file}"
    )


def _split_paths(value: str) -> list[Path]:
    return [Path(item.strip()) for item in value.split(",") if item.strip()]
