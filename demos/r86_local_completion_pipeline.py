"""R8.6 fake-local completion pipeline demo; performs no network access."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from agent.artifacts.store import ArtifactStore
from agent.challenge.experience import ChallengeExperienceManager
from agent.challenge.importer import ChallengeImporter
from agent.completion.collector import ChallengeCompletionPipeline
from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.models import ExperimentStatus
from agent.intelligence.models import ArtifactReference, Confidence, Fact, HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import RunState, RunStatus
from agent.workspace.manager import WorkspaceManager


DEMO_TOKEN = "LOCAL_COMPLETION_PIPELINE_OK"


def run_demo(root: str | Path) -> str:
    """Import, fake a completed run, and consolidate evidence locally."""

    root_path = Path(root)
    experience_root = root_path / "experiences" / "challenges"
    imported = ChallengeImporter(
        workspace_root=root_path / "workspace",
        experience_root=experience_root,
        source_root=root_path,
    ).import_challenge(
        name="r86_fake_sqlite",
        domain="web",
        description="Authorized fake local SQLite challenge for completion validation.",
        target_url="http://127.0.0.1:5000",
        authorization_scope="authorized_local_demo",
        created_at="2026-08-24T00:00:00+00:00",
        entropy="r86-local-demo",
    )
    manifest = imported.manifest
    workspace = imported.workspace.workspace
    evidence_path = workspace.output_dir / "fake-sqlite-response.txt"
    evidence_path.write_text(
        "fake response references sqlite_master",
        encoding="utf-8",
    )
    artifact = ArtifactStore(workspace).register(
        evidence_path,
        created_by="fake_local_web",
        source_step=1,
        artifact_type="http_response",
    )

    intelligence = IntelligenceStore.create(manifest.challenge_id)
    intelligence.state.facts.append(
        Fact(
            category="database",
            content="SQLite behavior observed in a captured local response",
            confidence=Confidence.HIGH,
            artifact_refs=[ArtifactReference(artifact.artifact_id, "evidence_for")],
        )
    )
    experiments = ExperimentManager(intelligence)
    hypothesis = experiments.create_hypothesis(
        "The fake local parameter may expose SQLite-specific behavior",
        "web",
        0.5,
    )
    experiment = experiments.create_experiment(
        hypothesis.id,
        "identify SQLite catalog behavior in the captured response",
        {"tool_name": "fake_local_web", "arguments": {"case": "catalog"}},
        "the stored response references the SQLite catalog",
    )
    experiments.start_experiment(experiment.experiment_id)
    evidence = experiments.record_evidence(
        experiment.experiment_id,
        source="fake local response artifact",
        observation="captured response references sqlite_master",
        artifact_refs=[ArtifactReference(artifact.artifact_id, "evidence_for")],
    )
    experiments.record_result(
        experiment.experiment_id,
        "sqlite_master reference observed",
    )
    experiments.close_experiment(experiment.experiment_id, ExperimentStatus.SUCCESS)
    experiments.close_hypothesis(
        hypothesis.id,
        HypothesisStatus.CONFIRMED,
        [evidence.evidence_id],
    )

    run_state = RunState(manifest.to_challenge_spec(), run_id="r86-local-run")
    run_state.status = RunStatus.SOLVED
    manager = ChallengeExperienceManager(experience_root)
    binding = manager.start_run(manifest)
    workspace_manager = WorkspaceManager(root_path / "workspace")
    manager.complete_run(
        manifest,
        binding,
        run_state=run_state,
        intelligence_state=intelligence.state,
        artifacts=[artifact],
        workspace=workspace,
        workspace_manager=workspace_manager,
        checkpoint_path=None,
        result="SOLVED",
    )
    output = ChallengeCompletionPipeline().complete(
        manifest,
        run_state,
        intelligence.state,
        [artifact],
        experience_root=experience_root,
    )
    if not output.report_path.is_file() or not output.writeup_path.is_file():
        raise RuntimeError("completion documents were not generated")
    if not output.candidates or output.candidates[0].category != "sql_injection":
        raise RuntimeError("sanitized SQLite experience candidate was not generated")
    return DEMO_TOKEN


def main() -> None:
    with TemporaryDirectory(prefix="agonionce-r86-") as directory:
        print(run_demo(Path(directory)))


if __name__ == "__main__":
    main()
