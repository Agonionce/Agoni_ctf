"""R13 fake-local Web benchmark evaluation and performance reporting."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agent.domains.web.benchmark import (
    WebBenchmarkLoader,
    WebBenchmarkReportBuilder,
    WebBenchmarkRunner,
)
from agent.experience.quality import ExperienceQualityStore
from agent.experience.store import DEFAULT_EXPERIENCE_PATH, ExperienceStore


app = typer.Typer(help="R13 fake-local benchmark evaluation and reporting")


@app.command("list")
def list_benchmarks(
    root: Path = typer.Option(Path("benchmarks/web"), help="Benchmark fixture root"),
) -> None:
    """List contained fake-local Web benchmarks."""

    table = Table(title="Web Benchmarks")
    table.add_column("ID", style="cyan")
    table.add_column("Category")
    table.add_column("Name")
    for case in WebBenchmarkLoader(root).list():
        table.add_row(case.benchmark_id, case.category, case.name)
    Console().print(table)


@app.command("run")
def run_benchmark(
    benchmark_id: str = typer.Argument(..., help="Fake-local benchmark ID"),
    root: Path = typer.Option(Path("benchmarks/web"), help="Benchmark fixture root"),
    result_dir: Path = typer.Option(
        Path("benchmark-results/web"),
        help="Ignored local evaluation-record directory",
    ),
    experience: list[str] | None = typer.Option(
        None,
        "--experience",
        help="Approved Experience ID used by the run; may be repeated",
    ),
    apply_feedback: bool = typer.Option(
        False,
        "--apply-feedback",
        help="Explicitly update quality for listed approved Experience records",
    ),
    experience_store: Path = typer.Option(
        DEFAULT_EXPERIENCE_PATH,
        help="Approved global Experience JSON",
    ),
) -> None:
    """Evaluate static captures and persist one auditable Evaluation Record."""

    usage = tuple(experience or ())
    if apply_feedback and not usage:
        raise typer.BadParameter("--apply-feedback requires at least one --experience")
    loader = WebBenchmarkLoader(root)
    approved = ExperienceStore(experience_store)
    quality = ExperienceQualityStore.for_experience_path(experience_store)
    try:
        result = WebBenchmarkRunner(loader).run(
            loader.load(benchmark_id),
            result_root=result_dir,
            experience_usage=usage,
            experience_store=approved,
            quality_store=quality,
            apply_experience_feedback=apply_feedback,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise typer.BadParameter(str(error)) from error
    evaluation = result.evaluation
    Console().print(
        f"[{'green' if result.passed else 'red'}]Benchmark {result.status}[/]: "
        f"{benchmark_id} -> {result_dir}"
    )
    if evaluation is not None:
        typer.echo(
            f"Evaluation {evaluation.evaluation_id}; solved={evaluation.solved}; "
            f"experiments={len(evaluation.experiments)}; "
            f"evidence={len(evaluation.evidence)}; "
            f"experience={len(evaluation.experience_usage)}"
        )
    if not result.passed:
        raise typer.Exit(code=1)


@app.command("report")
def report_benchmarks(
    result_dir: Path = typer.Option(
        Path("benchmark-results/web"),
        help="Evaluation-record directory",
    ),
) -> None:
    """Aggregate success, experiment, time, Tool, and Experience metrics."""

    try:
        report = WebBenchmarkReportBuilder().from_directory(result_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise typer.BadParameter(str(error)) from error
    table = Table(title="Web Benchmark Performance")
    table.add_column("Metric", style="cyan")
    table.add_column("Value")
    rows = (
        ("Total challenges", str(report.total_challenges)),
        ("Total runs", str(report.total_runs)),
        ("Solved runs", str(report.solved_runs)),
        ("Success rate", f"{report.success_rate:.1%}"),
        ("Average experiments", f"{report.average_experiments:.2f}"),
        ("Average evidence", f"{report.average_evidence:.2f}"),
        ("Average time", f"{report.average_duration_seconds:.4f}s"),
        ("Tool calls", str(report.total_tool_calls)),
        ("Experience usage", str(report.experience_usage_count)),
        ("Experience usage rate", f"{report.experience_usage_rate:.1%}"),
        ("Improvement trend", f"{report.improvement_trend} ({report.improvement_delta:+.1%})"),
    )
    for name, value in rows:
        table.add_row(name, value)
    Console().print(table)
