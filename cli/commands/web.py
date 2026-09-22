"""Read-only R8 Web Runtime and attack-surface inspection."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agent.domains.manager import build_default_runtime_manager
from agent.domains.web.state import WebRuntimeState
from agent.domains.web.benchmark import WebBenchmarkLoader, WebBenchmarkRunner
from agent.domains.web.research.context import WebResearchContextBuilder
from agent.domains.web.research.models import redact_web_context_text
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from config import Config

app = typer.Typer(help="R12 authorized local Web research and benchmark inspection")


def _checkpoint_root() -> str:
    try:
        config = Config.load_config()
    except ValueError:
        return "./checkpoints"
    root = config.get("checkpoint_dir", "./checkpoints")
    return root if isinstance(root, str) else "./checkpoints"


def _load_web_state(checkpoint_path: str | None) -> WebRuntimeState | None:
    checkpoint = (
        IntelligenceCheckpoint(checkpoint_path)
        if checkpoint_path is not None
        else IntelligenceCheckpoint.latest(_checkpoint_root())
    )
    if checkpoint is None:
        typer.echo("尚无活动 checkpoint，无法显示 Web Runtime 状态")
        return None
    data = checkpoint.load()
    saved = data.domain_runtime_state
    if saved is None or saved.domain != "web":
        typer.echo("最新 checkpoint 不包含 Web Runtime 状态")
        return None
    manager = build_default_runtime_manager()
    state = manager.initialize("web", data.run_state.challenge, saved)
    assert isinstance(state, WebRuntimeState)
    return state


@app.command("status")
def status_command(
    checkpoint: str | None = typer.Option(None, help="Checkpoint directory"),
) -> None:
    """Display masked WebRuntimeState from a local checkpoint."""

    state = _load_web_state(checkpoint)
    if state is None:
        return
    table = Table(title="Web Runtime Status")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Phase", state.current_phase)
    table.add_row("Base URL", state.base_url or "-")
    table.add_row("Endpoints", ", ".join(state.endpoints) or "-")
    table.add_row("Parameters", ", ".join(sorted(state.parameters)) or "-")
    table.add_row("Cookies", ", ".join(sorted(state.cookies)) or "-")
    table.add_row("Technologies", ", ".join(state.technologies) or "-")
    Console().print(table)


@app.command("surface")
def surface_command(
    checkpoint: str | None = typer.Option(None, help="Checkpoint directory"),
) -> None:
    """Display the bounded passive Web attack surface."""

    state = _load_web_state(checkpoint)
    if state is None:
        return
    surface = state.web_intelligence.attack_surface
    table = Table(title="Web Attack Surface")
    table.add_column("Endpoints", style="cyan")
    table.add_column("Parameters")
    table.add_column("Technologies")
    table.add_row(
        str(len(surface.endpoints)),
        ", ".join(surface.parameters) or "-",
        ", ".join(surface.technologies) or "-",
    )
    Console().print(table)


@app.command("endpoints")
def endpoints_command(
    checkpoint: str | None = typer.Option(None, help="Checkpoint directory"),
) -> None:
    """List evidence-backed endpoint findings."""

    state = _load_web_state(checkpoint)
    if state is None:
        return
    table = Table(title="Web Endpoints")
    table.add_column("Method", style="cyan")
    table.add_column("Path")
    table.add_column("Parameters")
    table.add_column("Confidence")
    table.add_column("Source")
    for item in state.web_intelligence.attack_surface.endpoints:
        table.add_row(
            item.method,
            item.path,
            ", ".join(item.parameters) or "-",
            item.confidence.value,
            item.source,
        )
    Console().print(table)


@app.command("technologies")
def technologies_command(
    checkpoint: str | None = typer.Option(None, help="Checkpoint directory"),
) -> None:
    """List technology indicators as evidence, not confirmed vulnerabilities."""

    state = _load_web_state(checkpoint)
    if state is None:
        return
    table = Table(title="Web Technology Evidence")
    table.add_column("Technology", style="cyan")
    table.add_column("Confidence")
    table.add_column("Evidence")
    table.add_column("Source")
    for item in state.web_intelligence.technology_evidence:
        table.add_row(item.technology, item.confidence, item.evidence, item.source)
    Console().print(table)


@app.command("model")
def model_command(
    checkpoint: str | None = typer.Option(None, help="Checkpoint directory"),
) -> None:
    """Display the bounded R11 Web application model."""

    state = _load_web_state(checkpoint)
    if state is None:
        return
    table = Table(title="Web Application Model")
    table.add_column("Endpoint", style="cyan")
    table.add_column("Methods")
    table.add_column("Parameters")
    table.add_column("Statuses")
    table.add_column("Auth Required")
    for item in state.application_model.endpoints:
        table.add_row(
            item.path,
            ", ".join(item.methods) or "-",
            ", ".join(item.parameters) or "-",
            ", ".join(str(value) for value in item.status_codes) or "-",
            str(item.authentication_required) if item.authentication_required is not None else "unknown",
        )
    Console().print(table)
    typer.echo(
        "Authentication: "
        f"{state.application_model.authentication.status.value}; "
        f"technologies: {', '.join(item.name for item in state.application_model.technologies) or '-'}; "
        f"relationships: {len(state.application_model.relationships)}"
    )


@app.command("sessions")
def sessions_command(
    checkpoint: str | None = typer.Option(None, help="Checkpoint directory"),
) -> None:
    """List masked Web sessions without cookie, header, or CSRF values."""

    state = _load_web_state(checkpoint)
    if state is None:
        return
    table = Table(title="Web Sessions (values masked)")
    table.add_column("Session", style="cyan")
    table.add_column("Origin")
    table.add_column("Status")
    table.add_column("Authentication")
    table.add_column("Cookies")
    table.add_column("CSRF names")
    for item in state.sessions:
        safe = item.safe_dict()
        table.add_row(
            item.session_id,
            item.origin,
            item.status.value,
            item.authentication_status.value,
            ", ".join(safe["cookie_names"]) or "-",
            ", ".join(safe["csrf_token_names"]) or "-",
        )
    Console().print(table)


@app.command("experiments")
def experiments_command(
    checkpoint: str | None = typer.Option(None, help="Checkpoint directory"),
) -> None:
    """List Web-specific views of controlled experiments."""

    state = _load_web_state(checkpoint)
    if state is None:
        return
    table = Table(title="Web Research Experiments")
    table.add_column("Experiment", style="cyan")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Evaluation")
    table.add_column("Evidence")
    table.add_column("Goal")
    for item in state.web_experiments:
        table.add_row(
            item.experiment_id,
            item.experiment_type.value,
            item.status,
            item.evaluation or "-",
            str(len(item.evidence_ids)),
            redact_web_context_text(item.goal),
        )
    Console().print(table)


@app.command("findings")
def findings_command(
    checkpoint: str | None = typer.Option(None, help="Checkpoint directory"),
) -> None:
    """Show structured Web evidence and masked flag-candidate state."""

    state = _load_web_state(checkpoint)
    if state is None:
        return
    table = Table(title="Web Structured Evidence")
    table.add_column("Evidence", style="cyan")
    table.add_column("Type")
    table.add_column("Endpoint")
    table.add_column("Observation")
    table.add_column("Artifacts")
    for item in state.web_evidence:
        table.add_row(
            item.evidence_id,
            item.evidence_type.value,
            item.endpoint or "-",
            redact_web_context_text(item.observation),
            str(len(item.artifact_refs)),
        )
    Console().print(table)
    flags = Table(title="Web Flag Candidates (values masked)")
    flags.add_column("Candidate", style="cyan")
    flags.add_column("Digest")
    flags.add_column("Status")
    flags.add_column("Evidence")
    for item in state.flag_candidates:
        safe = item.safe_dict()
        flags.add_row(
            item.candidate_id,
            str(safe["value_digest"]),
            item.verification_status.value,
            str(len(item.artifact_refs)),
        )
    Console().print(flags)


@app.command("context")
def context_command(
    checkpoint: str | None = typer.Option(None, help="Checkpoint directory"),
    limit: int = typer.Option(5, min=1, max=20, help="Maximum items per context section"),
) -> None:
    """Show the bounded, sanitized Web research context supplied to planning."""

    state = _load_web_state(checkpoint)
    if state is None:
        return
    context = WebResearchContextBuilder(item_limit=limit).build(
        state,
        intelligence={
            "facts": "available through IntelligenceState",
            "web_evidence_count": len(state.web_evidence),
        },
        previous_experiments=state.web_experiments,
    )
    typer.echo(json.dumps(context, ensure_ascii=False, indent=2))


@app.command("benchmark")
def benchmark_command(
    benchmark_id: str | None = typer.Argument(None, help="Fake-local benchmark ID"),
    root: Path = typer.Option(Path("benchmarks/web"), help="Benchmark fixture root"),
    result_dir: Path = typer.Option(
        Path("benchmark-results/web"),
        help="Ignored directory for local result records",
    ),
) -> None:
    """List or evaluate static fake-local Web benchmark captures."""

    loader = WebBenchmarkLoader(root)
    if benchmark_id is None:
        table = Table(title="Fake-local Web Benchmarks")
        table.add_column("ID", style="cyan")
        table.add_column("Category")
        table.add_column("Name")
        for case in loader.list():
            table.add_row(case.benchmark_id, case.category, case.name)
        Console().print(table)
        return
    try:
        case = loader.load(benchmark_id)
        result = WebBenchmarkRunner(loader).run(case, result_root=result_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise typer.BadParameter(str(error)) from error
    table = Table(title=f"Web Benchmark: {case.name}")
    table.add_column("Expectation", style="cyan")
    table.add_column("Result")
    table.add_column("Observation")
    for check in result.checks:
        table.add_row(
            str(check.expectation.get("kind", "unknown")),
            "PASS" if check.passed else "FAIL",
            check.observation,
        )
    Console().print(table)
    typer.echo(f"Result: {result.status}")
    if not result.passed:
        raise typer.Exit(code=1)
