"""Read-only R7 global experience memory commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agent.experience.store import DEFAULT_EXPERIENCE_PATH, ExperienceStore
from agent.experience.quality import (
    ExperienceFeedbackManager,
    ExperienceFeedbackOutcome,
    ExperienceQualityStore,
)
from agent.completion.experience import ExperienceCandidateCatalog
from config import Config


app = typer.Typer(help="R13 reviewed memory, quality, and effectiveness")
candidates_app = typer.Typer(help="R8.6 reviewed experience candidate workflow")
app.add_typer(candidates_app, name="candidates")


def _store_path(path: Path | None) -> Path:
    if path is not None:
        return path
    config = Config.load_config()
    experience = config.get("experience")
    configured = (
        experience.get("path", str(DEFAULT_EXPERIENCE_PATH))
        if isinstance(experience, dict)
        else str(DEFAULT_EXPERIENCE_PATH)
    )
    if not isinstance(configured, str) or not configured.strip():
        raise typer.BadParameter("experience.path must be a non-empty string")
    return Path(configured)


def _table(title: str) -> Table:
    table = Table(title=title)
    table.add_column("ID", style="cyan", width=18, no_wrap=True)
    table.add_column("Domain")
    table.add_column("Category", style="green")
    table.add_column("Pattern")
    table.add_column("Confidence")
    table.add_column("Source Run")
    table.add_column("Uses")
    table.add_column("Effectiveness")
    return table


def _render(records, title: str, quality_store: ExperienceQualityStore | None = None) -> None:
    table = _table(title)
    for item in records:
        quality = quality_store.get(item.id) if quality_store is not None else None
        table.add_row(
            item.id,
            item.domain,
            item.category,
            item.pattern,
            f"{item.confidence:.2f}",
            item.source_run,
            str(quality.use_count) if quality is not None else "0",
            f"{quality.effectiveness:.2f}" if quality is not None else "-",
        )
    Console().print(table)


@app.command("list")
def list_experience(
    store: Path | None = typer.Option(
        None,
        "--store",
        help="Experience JSON path; defaults to configured global memory",
    ),
) -> None:
    """List global experience records without changing them."""

    path = _store_path(store)
    _render(
        ExperienceStore(path).list(),
        "Experience Memory",
        ExperienceQualityStore.for_experience_path(path),
    )


@app.command("search")
def search_experience(
    query: str = typer.Argument(..., help="Keyword query such as sql"),
    domain: str | None = typer.Option(None, "--domain", help="Optional domain filter"),
    limit: int = typer.Option(5, "--limit", min=1, help="Maximum records"),
    store: Path | None = typer.Option(
        None,
        "--store",
        help="Experience JSON path; defaults to configured global memory",
    ),
) -> None:
    """Search by domain, category, and plain keywords; no embeddings are used."""

    keywords = [item for item in query.lower().split() if item]
    records = ExperienceStore(_store_path(store)).query(
        domain=domain.lower() if domain else None,
        keywords=keywords,
        limit=limit,
    )
    _render(
        records,
        f"Experience Search: {query}",
        ExperienceQualityStore.for_experience_path(_store_path(store)),
    )


@app.command("feedback")
def record_feedback(
    experience_id: str = typer.Argument(..., help="Approved Experience ID"),
    outcome: str = typer.Option(..., help="SUCCESS, FAILURE, or INCONCLUSIVE"),
    source_run: str = typer.Option(..., help="Opaque source Run ID"),
    source_challenge: str = typer.Option(..., help="Opaque source Challenge ID"),
    solved: bool = typer.Option(False, "--solved/--not-solved"),
    evidence: list[str] | None = typer.Option(
        None,
        "--evidence",
        help="Opaque evidence ID; may be repeated",
    ),
    store: Path = typer.Option(
        DEFAULT_EXPERIENCE_PATH,
        "--store",
        help="Approved global Experience JSON",
    ),
) -> None:
    """Explicitly record the result of using one approved Experience."""

    try:
        feedback_outcome = ExperienceFeedbackOutcome(outcome.upper())
        quality = ExperienceFeedbackManager(
            ExperienceStore(store),
            ExperienceQualityStore.for_experience_path(store),
        ).record(
            experience_id,
            source_run=source_run,
            source_challenge=source_challenge,
            outcome=feedback_outcome,
            solved=solved,
            evidence_refs=tuple(evidence or ()),
        )
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    Console().print(
        f"[green]Experience feedback recorded:[/green] {experience_id}; "
        f"uses={quality.use_count}; effectiveness={quality.effectiveness:.2f}; "
        f"confidence={quality.confidence:.2f}"
    )


@app.command("quality")
def show_quality(
    experience_id: str | None = typer.Argument(None, help="Optional Experience ID"),
    store: Path = typer.Option(
        DEFAULT_EXPERIENCE_PATH,
        "--store",
        help="Approved global Experience JSON",
    ),
) -> None:
    """Show provenance, usage, validation, and effectiveness metadata."""

    quality_store = ExperienceQualityStore.for_experience_path(store)
    records = quality_store.list()
    if experience_id is not None:
        records = [item for item in records if item.experience_id == experience_id]
    table = Table(title="Experience Quality")
    for name in (
        "Experience", "Source Challenge", "Evidence", "Uses",
        "Success", "Failure", "Effectiveness", "Confidence",
    ):
        table.add_column(name, style="cyan" if name == "Experience" else None)
    for item in records:
        table.add_row(
            item.experience_id,
            item.source_challenge,
            str(len(item.source_evidence)),
            str(item.use_count),
            str(item.success_count),
            str(item.failure_count),
            f"{item.effectiveness:.2f}",
            f"{item.confidence:.2f}",
        )
    Console().print(table)
    if records:
        typer.echo("Experience IDs: " + ", ".join(item.experience_id for item in records))


def _candidate_catalog(challenge_root: Path, global_store: Path) -> ExperienceCandidateCatalog:
    """Build the review catalog without reading config.json."""

    return ExperienceCandidateCatalog(challenge_root, global_store)


@candidates_app.command("list")
def list_candidates(
    challenge_root: Path = typer.Option(
        Path("experiences/challenges"),
        "--challenge-root",
        help="Per-challenge candidate root",
    ),
    global_store: Path = typer.Option(
        DEFAULT_EXPERIENCE_PATH,
        "--global-store",
        help="Reviewed global experience JSON",
    ),
) -> None:
    """List candidates and their review state without changing either store."""

    table = Table(title="Experience Candidates")
    table.add_column("ID", style="cyan", width=24, no_wrap=True)
    table.add_column("Challenge")
    table.add_column("Category", style="green")
    table.add_column("Status")
    table.add_column("Lesson")
    for item in _candidate_catalog(challenge_root, global_store).list():
        table.add_row(
            item.id,
            item.source_challenge,
            item.category,
            item.review_status.value,
            item.lesson,
        )
    Console().print(table)


@candidates_app.command("approve")
def approve_candidate(
    candidate_id: str = typer.Argument(..., help="Candidate ID"),
    challenge_root: Path = typer.Option(
        Path("experiences/challenges"),
        "--challenge-root",
    ),
    global_store: Path = typer.Option(
        DEFAULT_EXPERIENCE_PATH,
        "--global-store",
    ),
) -> None:
    """Approve one candidate and then add its sanitized record to global memory."""

    try:
        candidate = _candidate_catalog(challenge_root, global_store).approve(candidate_id)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    Console().print(
        f"[green]Candidate approved:[/green] {candidate.id} -> {global_store}"
    )


@candidates_app.command("reject")
def reject_candidate(
    candidate_id: str = typer.Argument(..., help="Candidate ID"),
    challenge_root: Path = typer.Option(
        Path("experiences/challenges"),
        "--challenge-root",
    ),
    global_store: Path = typer.Option(
        DEFAULT_EXPERIENCE_PATH,
        "--global-store",
    ),
) -> None:
    """Reject one candidate without writing global memory."""

    try:
        candidate = _candidate_catalog(challenge_root, global_store).reject(candidate_id)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    Console().print(f"[yellow]Candidate rejected:[/yellow] {candidate.id}")
