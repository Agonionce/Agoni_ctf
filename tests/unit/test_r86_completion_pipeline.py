from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent.challenge.experience import ChallengeExperienceManager
from agent.challenge.models import ChallengeManifest
from agent.completion.collector import ChallengeCompletionPipeline, CompletionCollector
from agent.completion.experience import (
    ExperienceCandidateCatalog,
    ExperienceCandidateExtractor,
)
from agent.completion.models import ExperienceCandidate, ExperienceReviewStatus
from agent.completion.report import ReportGenerator
from agent.completion.writeup import WriteupGenerator
from agent.experience.store import ExperienceStore
from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.models import ExperimentStatus
from agent.intelligence.models import ArtifactReference, Confidence, Fact, HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import (
    FlagCandidate,
    RunState,
    RunStatus,
    TerminationDecision,
    TerminationReason,
    to_jsonable,
)
from agent.workspace.manager import WorkspaceManager
from cli.app import app


runner = CliRunner()


def _manifest() -> ChallengeManifest:
    return ChallengeManifest(
        challenge_id="r86-local-sqlite",
        name="R8.6 Local SQLite",
        domain="web",
        description="Authorized fake local Web challenge.",
        target_url="http://127.0.0.1:5000",
        authorization_scope="local_ctf",
        created_at="2026-08-24T00:00:00+00:00",
    )


def _completed_state(manifest: ChallengeManifest):
    store = IntelligenceStore.create(manifest.challenge_id)
    store.state.facts.append(
        Fact(
            category="database",
            content="SQLite behavior observed",
            confidence=Confidence.HIGH,
            artifact_refs=[ArtifactReference("artifact-001", "evidence_for")],
        )
    )
    manager = ExperimentManager(store)
    hypothesis = manager.create_hypothesis(
        "The local id parameter may produce database-dependent behavior",
        "web",
        0.5,
    )
    experiment = manager.create_experiment(
        hypothesis.id,
        "identify the SQLite catalog behavior",
        {"tool_name": "fake_local_web", "arguments": {"case": "catalog"}},
        "the captured response references the SQLite catalog",
    )
    manager.start_experiment(experiment.experiment_id)
    evidence = manager.record_evidence(
        experiment.experiment_id,
        source="fake local response artifact",
        observation="response references sqlite_master in the captured database error",
        artifact_refs=[ArtifactReference("artifact-001", "evidence_for")],
    )
    manager.record_result(
        experiment.experiment_id,
        "sqlite_master reference observed in the fake response",
    )
    manager.close_experiment(experiment.experiment_id, ExperimentStatus.SUCCESS)
    manager.close_hypothesis(
        hypothesis.id,
        HypothesisStatus.CONFIRMED,
        [evidence.evidence_id],
    )
    run_state = RunState(manifest.to_challenge_spec(), run_id="run-r86-local")
    run_state.set_termination(
        TerminationDecision(
            status=RunStatus.SOLVED,
            reason=TerminationReason.FLAG_CONFIRMED,
            message="confirmed in fake local evidence",
            flag_candidate=FlagCandidate(
                value="FLAG{sqlite-answer}",
                source="fake local response artifact",
                confidence=0.96,
                evidence="The captured response matches the SQLite evidence.",
            ),
        )
    )
    artifacts = [
        {
            "artifact_id": "artifact-001",
            "path": "output/fake-response.txt",
            "created_by": "fake_local_web",
            "created_at": "2026-08-24T00:01:00+00:00",
            "source_step": 1,
            "artifact_type": "http_response",
        }
    ]
    return run_state, store, artifacts


def _bound_challenge(tmp_path: Path):
    manifest = _manifest()
    experience_root = tmp_path / "experiences" / "challenges"
    manager = ChallengeExperienceManager(experience_root)
    paths = manager.create(manifest)
    workspace_manager = WorkspaceManager(tmp_path / "workspace")
    workspace = workspace_manager.create(manifest.challenge_id)
    evidence_path = workspace.output_dir / "fake-response.txt"
    evidence_path.write_text("fake sqlite_master response", encoding="utf-8")
    run_state, store, artifacts = _completed_state(manifest)
    binding = manager.start_run(manifest)
    manager.complete_run(
        manifest,
        binding,
        run_state=run_state,
        intelligence_state=store.state,
        artifacts=artifacts,
        workspace=workspace,
        workspace_manager=workspace_manager,
        checkpoint_path=None,
        result="SOLVED",
    )
    return manifest, manager, paths, run_state, store, artifacts


def test_collector_report_and_writeup_are_evidence_bound_and_read_only(tmp_path):
    manifest, _manager, paths, run_state, store, artifacts = _bound_challenge(tmp_path)
    before_run = to_jsonable(run_state)
    before_intelligence = to_jsonable(store.state)

    report = CompletionCollector(clock=lambda: "2026-08-24T01:00:00+00:00").collect(
        manifest,
        run_state,
        store.state,
        artifacts,
    )
    report_text = ReportGenerator().generate(report, manifest=manifest)
    writeup_text = WriteupGenerator().generate(manifest, report)

    assert report.status == "SOLVED"
    assert report.evidence[0]["observation"] == (
        "response references sqlite_master in the captured database error"
    )
    for heading in (
        "## Overview",
        "## Domain",
        "## Timeline",
        "## Key Findings",
        "## Experiments",
        "## Evidence",
        "## Result",
        "## Lessons",
    ):
        assert heading in report_text
    for heading in (
        "## Challenge Description",
        "## Recon",
        "## Analysis",
        "## Exploitation Process",
        "## Evidence",
        "## Solution",
        "## Flag",
        "## Lessons Learned",
    ):
        assert heading in writeup_text
    assert report.evidence[0]["observation"] in report_text
    assert report.evidence[0]["observation"] in writeup_text
    assert "FLAG{sqlite-answer}" in report_text
    assert "FLAG{sqlite-answer}" in writeup_text
    assert "output/fake-response.txt" in report_text
    assert "invented exploitation step" not in writeup_text
    assert "Supporting evidence" in writeup_text
    assert to_jsonable(run_state) == before_run
    assert to_jsonable(store.state) == before_intelligence
    assert paths.report_file.name == "report.md"


def test_completion_pipeline_writes_layout_and_pending_candidate(tmp_path):
    manifest, manager, paths, run_state, store, artifacts = _bound_challenge(tmp_path)

    output = ChallengeCompletionPipeline().complete(
        manifest,
        run_state,
        store.state,
        artifacts,
        experience_root=manager.root,
    )

    assert output.report_path.is_file()
    assert output.writeup_path.is_file()
    assert output.lessons_path.is_file()
    assert output.candidates_path.is_file()
    assert len(output.candidates) == 1
    assert output.candidates[0].category == "sql_injection"
    assert output.candidates[0].review_status is ExperienceReviewStatus.PENDING
    raw = json.loads(paths.experience_candidates_file.read_text(encoding="utf-8"))
    assert raw["candidates"][0]["review_status"] == "PENDING"


def test_candidate_security_filter_and_approval_gate(tmp_path):
    manifest, manager, paths, run_state, store, artifacts = _bound_challenge(tmp_path)
    output = ChallengeCompletionPipeline().complete(
        manifest,
        run_state,
        store.state,
        artifacts,
        experience_root=manager.root,
    )
    candidate = output.candidates[0]
    global_path = tmp_path / "experiences" / "global" / "experience.json"
    catalog = ExperienceCandidateCatalog(manager.root, global_path)

    assert not global_path.exists()
    approved = catalog.approve(candidate.id)
    assert approved.review_status is ExperienceReviewStatus.APPROVED
    records = ExperienceStore(global_path).list()
    assert len(records) == 1
    assert catalog.approve(candidate.id).review_status is ExperienceReviewStatus.APPROVED
    assert len(ExperienceStore(global_path).list()) == 1
    serialized = json.dumps(records[0].to_dict()).lower()
    for prohibited in ("password", "token", "cookie", "secret", "flag", "credential"):
        assert prohibited not in serialized

    second = ExperienceCandidate(
        id="candidate-reject",
        category="sql_injection",
        pattern="Database behavior should be identified before query selection.",
        strategy="Compare controlled responses before the next experiment.",
        lesson="Identify database behavior before choosing a query strategy.",
        source_challenge=manifest.challenge_id,
        confidence=0.7,
    )
    from agent.completion.experience import ExperienceCandidateStore

    candidate_store = ExperienceCandidateStore(
        paths.experience_candidates_file,
        challenge_id=manifest.challenge_id,
    )
    candidate_store.replace_all([approved, second])
    rejected = catalog.reject(second.id)
    assert rejected.review_status is ExperienceReviewStatus.REJECTED
    assert len(ExperienceStore(global_path).list()) == 1

    with pytest.raises(ValueError, match="prohibited"):
        ExperienceCandidate(
            category="authentication",
            pattern="Reuse a cookie value from the prior challenge.",
            strategy="Compare responses.",
            lesson="Persist the observed state.",
            source_challenge=manifest.challenge_id,
            confidence=0.5,
        )
    with pytest.raises(ValueError, match="prohibited"):
        ExperienceCandidate(
            category="authentication",
            pattern="Analyze reusable access-control state.",
            strategy="Compare responses.",
            lesson="Persist the observed state.",
            source_challenge="private-secret-challenge",
            confidence=0.5,
        )


def test_sensitive_evidence_produces_no_experience_candidate(tmp_path):
    manifest, _manager, _paths, run_state, store, artifacts = _bound_challenge(tmp_path)
    store.state.evidence[0].observation += " with cookie material"
    report = CompletionCollector().collect(manifest, run_state, store.state, artifacts)

    assert ExperienceCandidateExtractor().extract(report, report.experiments, []) == []


@pytest.mark.parametrize(
    "private_text",
    [
        "HTB{candidate-value}",
        "picoCTF{candidate-value}",
        "Authorization: opaquecredential123456",
        "X-API-Key: abcdefghijklmnop",
        "/Users/maxchen/private/app.py",
        "/tmp/challenge-output.txt",
        r"C:\private\challenge-output.txt",
        r"\\server\share\challenge-output.txt",
        "Use HTTPRequestTool with arguments payload",
    ],
)
def test_experience_candidate_rejects_extended_private_values(private_text):
    with pytest.raises(ValueError, match="prohibited"):
        ExperienceCandidate(
            category="authentication",
            pattern="Compare a stable local response.",
            strategy="Change one controlled variable.",
            lesson=private_text,
            source_challenge="challenge-safe-fixture",
            confidence=0.5,
        )


def test_candidate_approval_rechecks_safety_before_global_write(tmp_path, monkeypatch):
    candidate = ExperienceCandidate(
        id="candidate-defense-in-depth",
        category="authentication",
        pattern="Compare a stable local response.",
        strategy="Change one controlled variable.",
        lesson="Keep evidence separate from its explanation.",
        source_challenge="challenge-safe-fixture",
        confidence=0.5,
    )
    object.__setattr__(candidate, "lesson", "HTB{candidate-value}")
    global_path = tmp_path / "experiences" / "global" / "experience.json"
    catalog = ExperienceCandidateCatalog(tmp_path / "challenges", global_path)
    monkeypatch.setattr(catalog, "_locate", lambda _candidate_id: (object(), candidate))

    with pytest.raises(ValueError, match="prohibited"):
        catalog.approve(candidate.id)
    assert not global_path.exists()


def test_completion_cli_report_writeup_extract_list_approve_and_reject(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "cli.commands.experience.Config.load_config",
        lambda: (_ for _ in ()).throw(AssertionError("config.json must not be read")),
    )
    manifest, manager, paths, _run_state, _store, _artifacts = _bound_challenge(tmp_path)
    root = manager.root
    report = runner.invoke(
        app,
        ["challenge", "report", manifest.challenge_id, "--experience-root", str(root)],
    )
    writeup = runner.invoke(
        app,
        ["challenge", "writeup", manifest.challenge_id, "--experience-root", str(root)],
    )
    extract = runner.invoke(
        app,
        [
            "challenge",
            "extract-experience",
            manifest.challenge_id,
            "--experience-root",
            str(root),
        ],
    )
    assert report.exit_code == 0, report.stdout
    assert writeup.exit_code == 0, writeup.stdout
    assert extract.exit_code == 0, extract.stdout
    assert paths.report_file.is_file()
    assert paths.writeup_file.is_file()

    candidates = ExperienceCandidateCatalog(root).list()
    assert len(candidates) == 1
    listed = runner.invoke(
        app,
        ["experience", "candidates", "list", "--challenge-root", str(root)],
    )
    assert listed.exit_code == 0, listed.stdout
    assert candidates[0].id in listed.stdout.replace("\n", "")

    global_path = tmp_path / "global" / "experience.json"
    approved = runner.invoke(
        app,
        [
            "experience",
            "candidates",
            "approve",
            candidates[0].id,
            "--challenge-root",
            str(root),
            "--global-store",
            str(global_path),
        ],
    )
    assert approved.exit_code == 0, approved.stdout
    assert len(ExperienceStore(global_path).list()) == 1
