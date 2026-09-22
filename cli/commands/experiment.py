"""Read-only experiment, evidence, and R10.2 research-loop inspection."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agent.intelligence.checkpoint import (
    IntelligenceCheckpoint,
    IntelligenceCheckpointData,
)
from agent.intelligence.store import IntelligenceStore
from config import Config


experiment_app = typer.Typer(help="R10.2 experiment runtime and research loop")
hypothesis_app = typer.Typer(help="R10.2 hypothesis state")
evidence_app = typer.Typer(help="R6 evidence state")


def _load_checkpoint(
    checkpoint: Path | None,
) -> IntelligenceCheckpointData | None:
    checkpoint_store: IntelligenceCheckpoint | None
    if checkpoint is not None:
        checkpoint_store = IntelligenceCheckpoint(checkpoint)
    else:
        config = Config.load_config()
        checkpoint_dir = config.get("checkpoint_dir", "./checkpoints")
        root = checkpoint_dir if isinstance(checkpoint_dir, str) else "./checkpoints"
        checkpoint_store = IntelligenceCheckpoint.latest(root)
    if checkpoint_store is None:
        return None
    return checkpoint_store.load()


def _load_store(checkpoint: Path | None) -> IntelligenceStore | None:
    data = _load_checkpoint(checkpoint)
    return data.intelligence_store if data is not None else None


def _value(value: object) -> str:
    return str(value.value) if isinstance(value, Enum) else str(value)


@experiment_app.command("list")
def list_experiments(
    checkpoint: Path | None = typer.Option(
        None,
        "--checkpoint",
        help="Checkpoint directory; defaults to the latest checkpoint",
    ),
) -> None:
    """List experiments without executing a Tool."""

    store = _load_store(checkpoint)
    console = Console()
    if store is None:
        console.print("[yellow]No experiment checkpoint found[/yellow]")
        return
    table = Table(title="Experiments")
    table.add_column("ID", style="cyan")
    table.add_column("Hypothesis")
    table.add_column("Status", style="green")
    table.add_column("Goal")
    table.add_column("Expected / Actual")
    for item in store.state.experiments:
        outcome = item.expected_result
        if item.actual_result:
            outcome = f"{outcome} / {item.actual_result}"
        table.add_row(
            item.experiment_id,
            item.hypothesis_id,
            item.status.value,
            item.goal,
            outcome,
        )
    console.print(table)


@experiment_app.command("status")
def experiment_status(
    checkpoint: Path | None = typer.Option(
        None,
        "--checkpoint",
        help="Checkpoint directory; defaults to the latest checkpoint",
    ),
) -> None:
    """Show hypothesis binding, runtime state, and evidence counts."""

    data = _load_checkpoint(checkpoint)
    console = Console()
    if data is None:
        console.print("[yellow]No experiment checkpoint found[/yellow]")
        return
    store = data.intelligence_store
    runtime_state = data.experiment_runtime_state
    table = Table(title="Experiment Runtime Status")
    table.add_column("Hypothesis", style="cyan")
    table.add_column("Experiment")
    table.add_column("Status", style="green")
    table.add_column("Evidence")
    table.add_column("Evaluation")
    if runtime_state is not None:
        for record in runtime_state.records:
            table.add_row(
                record.hypothesis_id,
                record.experiment_id,
                record.status.value,
                f"{len(record.evidence_ids)} evidence",
                record.evaluation.status.value if record.evaluation else "-",
            )
    else:
        for experiment in store.state.experiments:
            evidence_count = sum(
                item.experiment_id == experiment.experiment_id
                for item in store.state.evidence
            )
            table.add_row(
                experiment.hypothesis_id,
                experiment.experiment_id,
                experiment.status.value,
                f"{evidence_count} evidence",
                "legacy R6 state",
            )
    console.print(table)


@experiment_app.command("loop")
def experiment_loop(
    checkpoint: Path | None = typer.Option(
        None,
        "--checkpoint",
        help="Checkpoint directory; defaults to the latest checkpoint",
    ),
) -> None:
    """Show the bounded autonomous research loop and its next recommendation."""

    data = _load_checkpoint(checkpoint)
    console = Console()
    if data is None or data.experiment_runtime_state is None:
        console.print("[yellow]No autonomous experiment loop checkpoint found[/yellow]")
        return
    state = data.experiment_runtime_state
    console.print(
        f"Experiment loop iteration: [cyan]{state.loop_iteration}[/cyan] | "
        f"active hypotheses: {len(state.active_hypothesis_ids)} | "
        f"pending runtime experiments: {len(state.pending())}"
    )
    table = Table(title="Autonomous Experiment Loop")
    table.add_column("Rank")
    table.add_column("Hypothesis", style="cyan")
    table.add_column("Source")
    table.add_column("Priority")
    table.add_column("Score")
    table.add_column("Next experiment goal")
    table.add_column("Experience")
    for rank, item in enumerate(state.active_candidates, start=1):
        table.add_row(
            str(rank),
            item.hypothesis_id,
            item.source.value,
            item.priority.value,
            f"{item.score:.4f}",
            item.suggested_goal,
            ", ".join(item.experience_influence) or "-",
        )
    console.print(table)
    if state.decision_history:
        latest = state.decision_history[-1]
        console.print(
            f"Latest decision: [green]{latest.decision}[/green] "
            f"for {latest.hypothesis_id or '-'}"
        )


@experiment_app.command("history")
def experiment_history(
    checkpoint: Path | None = typer.Option(
        None,
        "--checkpoint",
        help="Checkpoint directory; defaults to the latest checkpoint",
    ),
) -> None:
    """Show experiment execution, evaluation, and feedback history."""

    data = _load_checkpoint(checkpoint)
    console = Console()
    if data is None or data.experiment_runtime_state is None:
        console.print("[yellow]No experiment history checkpoint found[/yellow]")
        return
    table = Table(title="Experiment History")
    table.add_column("Step")
    table.add_column("Hypothesis", style="cyan")
    table.add_column("Experiment")
    table.add_column("Runtime")
    table.add_column("Evaluation", style="green")
    table.add_column("Evidence")
    table.add_column("Feedback")
    for item in data.experiment_runtime_state.records:
        table.add_row(
            str(item.step_id),
            item.hypothesis_id,
            item.experiment_id,
            item.status.value,
            item.evaluation.status.value if item.evaluation else "-",
            str(len(item.evidence_ids)),
            (
                str(item.feedback.get("hypothesis_status", "applied"))
                if item.feedback_applied
                else "-"
            ),
        )
    console.print(table)


@hypothesis_app.command("list")
def list_hypotheses(
    checkpoint: Path | None = typer.Option(
        None,
        "--checkpoint",
        help="Checkpoint directory; defaults to the latest checkpoint",
    ),
) -> None:
    """List current and closed hypotheses without executing a Tool."""

    store = _load_store(checkpoint)
    console = Console()
    if store is None:
        console.print("[yellow]No hypothesis checkpoint found[/yellow]")
        return
    table = Table(title="Hypotheses")
    table.add_column("Status", style="green", no_wrap=True)
    table.add_column("ID", style="cyan")
    table.add_column("Domain")
    table.add_column("Confidence")
    table.add_column("Source / Priority")
    table.add_column("Statement")
    table.add_column("Provenance")
    for item in store.state.hypotheses:
        provenance = [
            *(reference.artifact_id for reference in item.related_artifacts),
            *item.evidence_refs,
        ]
        table.add_row(
            item.status.value,
            item.id,
            item.domain,
            _value(item.confidence),
            f"{item.source.value} / {item.priority.value}",
            item.statement,
            ", ".join(provenance) or "-",
        )
    console.print(table)


@evidence_app.command("list")
def list_evidence(
    checkpoint: Path | None = typer.Option(
        None,
        "--checkpoint",
        help="Checkpoint directory; defaults to the latest checkpoint",
    ),
) -> None:
    """List observations as evidence without presenting them as conclusions."""

    store = _load_store(checkpoint)
    console = Console()
    if store is None:
        console.print("[yellow]No evidence checkpoint found[/yellow]")
        return
    table = Table(title="Evidence")
    table.add_column("ID", style="cyan")
    table.add_column("Experiment")
    table.add_column("Source")
    table.add_column("Observation")
    table.add_column("Artifacts", width=12, no_wrap=True)
    table.add_column("Timestamp")
    for item in store.state.evidence:
        table.add_row(
            item.evidence_id,
            item.experiment_id,
            item.source,
            item.observation,
            ", ".join(reference.artifact_id for reference in item.artifact_refs) or "-",
            item.timestamp,
        )
    console.print(table)
