from __future__ import annotations

import json
import re
from pathlib import Path
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from agent.artifacts.store import ArtifactStore
from agent.challenge.experience import ChallengeExperienceManager
from agent.challenge.importer import ChallengeImporter
from agent.challenge.models import ChallengeManifest, new_challenge_id
from agent.challenge.validator import ChallengeSecurityError, slugify_name
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import RunState, RunStatus
from agent.workflow import Workflow
from agent.workspace.manager import WorkspaceManager
from cli.app import app


runner = CliRunner()


def _fixture_inputs(root: Path) -> tuple[Path, Path]:
    source = root / "source"
    source.mkdir()
    (source / "app.py").write_text("print('fake local app')\n", encoding="utf-8")
    archive = root / "challenge.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("README.txt", "fake local attachment")
    return archive, source


def _import(tmp_path: Path):
    intake_root = tmp_path / "intake"
    intake_root.mkdir()
    archive, source = _fixture_inputs(intake_root)
    importer = ChallengeImporter(
        workspace_root=tmp_path / "workspace",
        experience_root=tmp_path / "experiences" / "challenges",
        source_root=intake_root,
    )
    return importer.import_challenge(
        name="easy_sqlite",
        domain="web",
        description="Local authorized fake Web challenge.",
        target_url="http://127.0.0.1:5000",
        attachments=[archive],
        source_paths=[source],
        authorization_scope="local_ctf",
        created_at="2026-08-21T12:00:00+00:00",
        entropy="unit-test",
    )


def test_import_creates_manifest_workspace_inputs_artifacts_and_experience(tmp_path):
    result = _import(tmp_path)
    manifest = result.manifest
    workspace = result.workspace.workspace

    assert re.fullmatch(r"easy_sqlite-20260821-[0-9a-f]{6}", manifest.challenge_id)
    assert manifest.attachments == ("input/challenge.zip",)
    assert manifest.source_paths == ("input/source",)
    assert (workspace.input_dir / "challenge.zip").is_file()
    assert (workspace.input_dir / "source" / "app.py").is_file()
    assert workspace.work_dir.is_dir()
    assert workspace.output_dir.is_dir()
    assert workspace.logs_dir.is_dir()

    artifacts = ArtifactStore(workspace).list()
    assert [item.artifact_type for item in artifacts] == [
        "challenge_attachment",
        "challenge_source",
    ]
    assert [item.path for item in artifacts] == [
        "input/challenge.zip",
        "input/source/app.py",
    ]

    experience = result.experience
    expected_files = {
        "challenge.json",
        "description.md",
        "intelligence.json",
        "experiments.json",
        "analysis.md",
        "report.md",
        "writeup.md",
        "lessons.md",
        "experience_candidates.json",
    }
    assert expected_files <= {item.name for item in experience.root.iterdir()}
    assert experience.artifacts_dir.is_dir()
    assert experience.runs_dir.is_dir()
    manifest_raw = json.loads(experience.challenge_file.read_text(encoding="utf-8"))
    assert manifest_raw == manifest.to_dict()
    assert str(tmp_path / "intake") not in json.dumps(manifest_raw)
    writeup = experience.writeup_file.read_text(encoding="utf-8")
    for heading in (
        "## Overview",
        "## Recon",
        "## Analysis",
        "## Experiments",
        "## Evidence",
        "## Solution",
        "## Flag",
        "## Lessons Learned",
    ):
        assert heading in writeup


def test_manifest_converts_to_existing_runtime_contract_and_ids_do_not_reuse():
    created_at = "2026-08-21T12:00:00+00:00"
    first = new_challenge_id("same challenge", created_at=created_at, entropy="one")
    second = new_challenge_id("same challenge", created_at=created_at, entropy="two")
    assert first != second
    manifest = ChallengeManifest(
        challenge_id=first,
        name="same challenge",
        domain="web",
        description="Local authorized example.",
        target_url="http://127.0.0.1:8080",
        attachments=("input/example.zip",),
        source_paths=("input/source/app",),
        authorization_scope="local_ctf",
        created_at=created_at,
    )

    challenge = manifest.to_challenge_spec()

    assert challenge.challenge_id == first
    assert challenge.category == "web"
    assert challenge.authorization_scope == "local_ctf"
    assert challenge.metadata["base_url"] == manifest.target_url
    assert challenge.metadata["attachment_paths"] == [
        "workspace://input/example.zip"
    ]
    assert challenge.metadata["legacy_attachment_paths"] == ["input/example.zip"]


def test_unicode_display_name_gets_safe_internal_identifiers():
    created_at = "2026-08-21T12:00:00+00:00"

    pure_chinese = ChallengeManifest.create(
        name="旧站备份",
        domain="web",
        description="Authorized local Unicode name example.",
        created_at=created_at,
        entropy="unicode-name",
    )
    mixed = ChallengeManifest.create(
        name="旧站 backup",
        domain="web",
        description="Authorized local mixed name example.",
        created_at=created_at,
        entropy="mixed-name",
    )

    assert pure_chinese.name == "旧站备份"
    assert re.fullmatch(r"challenge-[0-9a-f]{8}-20260821-[0-9a-f]{6}", pure_chinese.challenge_id)
    assert re.fullmatch(r"backup-[0-9a-f]{8}-20260821-[0-9a-f]{6}", mixed.challenge_id)
    assert slugify_name("旧站备份") == slugify_name("旧站备份")
    assert slugify_name("甲 backup") != slugify_name("乙 backup")


def test_intake_rejects_escape_symlink_sensitive_file_and_manifest_secret(tmp_path):
    intake_root = tmp_path / "intake"
    intake_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    importer = ChallengeImporter(
        workspace_root=tmp_path / "workspace",
        experience_root=tmp_path / "experiences",
        source_root=intake_root,
    )

    with pytest.raises(ChallengeSecurityError, match="escapes"):
        importer.import_challenge(
            name="escape",
            domain="misc",
            description="Authorized local escape test.",
            attachments=[outside],
        )

    secret = intake_root / "config.json"
    secret.write_text("{}", encoding="utf-8")
    with pytest.raises(ChallengeSecurityError, match="sensitive file"):
        importer.import_challenge(
            name="secret-file",
            domain="misc",
            description="Authorized local sensitive-file test.",
            attachments=[secret],
        )

    link = intake_root / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pass
    else:
        with pytest.raises(ChallengeSecurityError, match="symbolic links"):
            importer.import_challenge(
                name="link",
                domain="misc",
                description="Authorized local symlink test.",
                attachments=[link],
            )

    with pytest.raises(ChallengeSecurityError, match="sensitive data"):
        ChallengeManifest.create(
            name="unsafe",
            domain="misc",
            description="The answer is flag{SYNTHETIC_TEST_ONLY}.",
        )


def test_challenge_experience_binds_multiple_runs_checkpoint_and_artifacts(tmp_path):
    imported = _import(tmp_path)
    manifest = imported.manifest
    manager = ChallengeExperienceManager(tmp_path / "experiences" / "challenges")
    workspace = imported.workspace.workspace
    workspace_manager = WorkspaceManager(tmp_path / "workspace")
    output = workspace.output_dir / "evidence.txt"
    output.write_text("fake evidence", encoding="utf-8")
    artifact = ArtifactStore(workspace).register(
        output,
        created_by="fake_local_test",
        source_step=1,
        artifact_type="evidence",
    )
    intelligence = IntelligenceStore.create(manifest.challenge_id)
    state = RunState(manifest.to_challenge_spec(), run_id="run-r85-test")
    state.status = RunStatus.SOLVED
    checkpoint = tmp_path / "checkpoints" / "r4_run-r85-test"
    IntelligenceCheckpoint(checkpoint).save(state, intelligence, [artifact])

    first = manager.start_run(manifest)
    manager.complete_run(
        manifest,
        first,
        run_state=state,
        intelligence_state=intelligence.state,
        artifacts=[artifact],
        workspace=workspace,
        workspace_manager=workspace_manager,
        checkpoint_path=checkpoint,
        result="SOLVED",
    )
    second = manager.start_run(manifest)

    assert first.root.name == "run-001"
    assert second.root.name == "run-002"
    assert (first.checkpoint_dir / "run.json").is_file()
    assert (first.artifacts_dir / "output" / "evidence.txt").is_file()
    assert (
        imported.experience.artifacts_dir
        / "run-001"
        / "output"
        / "evidence.txt"
    ).is_file()
    assert "run-r85-test" in first.result_file.read_text(encoding="utf-8")


def test_challenge_cli_create_list_show_and_solve_manifest_input(tmp_path, monkeypatch):
    intake_root = tmp_path / "intake"
    intake_root.mkdir()
    archive, source = _fixture_inputs(intake_root)
    workspace_root = tmp_path / "workspace"
    experience_root = tmp_path / "experiences" / "challenges"
    created = runner.invoke(
        app,
        [
            "challenge",
            "create",
            "--name",
            "cli_fake",
            "--description",
            "Authorized local CLI fixture.",
            "--domain",
            "web",
            "--url",
            "http://127.0.0.1:5000",
            "--attachment",
            str(archive),
            "--source",
            str(source),
            "--source-root",
            str(intake_root),
            "--workspace-root",
            str(workspace_root),
            "--experience-root",
            str(experience_root),
        ],
    )
    assert created.exit_code == 0, created.stdout
    manifest = ChallengeExperienceManager(experience_root).store.list()[0]

    listed = runner.invoke(
        app,
        ["challenge", "list", "--experience-root", str(experience_root)],
    )
    shown = runner.invoke(
        app,
        [
            "challenge",
            "show",
            manifest.challenge_id,
            "--workspace-root",
            str(workspace_root),
            "--experience-root",
            str(experience_root),
        ],
    )
    assert listed.exit_code == 0
    assert manifest.challenge_id in listed.stdout.replace("\n", "")
    assert shown.exit_code == 0
    assert "cli_fake" in shown.stdout
    assert "Workspace" in shown.stdout
    assert manifest.challenge_id in shown.stdout.replace("\n", "")

    captured = {}
    monkeypatch.setattr("cli.commands.solve.setup_logging", lambda: None)
    monkeypatch.setattr(
        "cli.commands.solve.Config.load_config",
        lambda: {
            "checkpoint_dir": str(tmp_path / "checkpoints"),
            "platform": {
                "inputer": {"type": "file", "file_path": "unused.txt"},
                "submitter": {"type": "manual"},
            },
        },
    )

    def fake_run_workflow(*, config, user_interface, question, resume_data):
        captured["question"] = question
        return "LOCAL_FAKE_SOLVE_OK"

    monkeypatch.setattr("cli.commands.solve.run_workflow", fake_run_workflow)
    solved = runner.invoke(
        app,
        [
            "solve",
            "--challenge",
            manifest.challenge_id,
            "--challenge-root",
            str(experience_root),
            "--manual",
            "--no-resume",
            "--plain",
        ],
    )
    assert solved.exit_code == 0, solved.stdout
    question = captured["question"]
    assert question.title == "cli_fake"
    assert question.url == "http://127.0.0.1:5000"
    assert question.metadata["challenge_id"] == manifest.challenge_id
    assert "LOCAL_FAKE_SOLVE_OK" in solved.stdout


def test_challenge_create_interactive_prompts_bootstrap_without_manual_paths(tmp_path):
    created = runner.invoke(
        app,
        [
            "challenge",
            "create",
            "--source-root",
            str(tmp_path),
            "--workspace-root",
            str(tmp_path / "workspace"),
            "--experience-root",
            str(tmp_path / "experiences" / "challenges"),
        ],
        input=(
            "interactive_fake\n"
            "Authorized local interactive fixture.\n"
            "web\n"
            "\n"
            "\n"
            "\n"
        ),
    )

    assert created.exit_code == 0, created.stdout
    assert "Challenge created" in created.stdout
    assert "interactive_fake-" in created.stdout.replace("\n", "")


def test_workflow_binds_imported_challenge_after_existing_checkpoint(tmp_path, monkeypatch):
    imported = _import(tmp_path)
    manifest = imported.manifest
    workspace = imported.workspace.workspace
    intelligence = IntelligenceStore.create(manifest.challenge_id)
    state = RunState(manifest.to_challenge_spec(), run_id="run-workflow-r85")
    state.status = RunStatus.SOLVED

    class FakeExecutor:
        def __init__(self):
            self.workspace_manager = WorkspaceManager(tmp_path / "workspace")

        def artifacts_for_current_workspace(self):
            return ArtifactStore(workspace).list()

    class FakeRuntime:
        def __init__(self):
            self.intelligence_store = intelligence
            self.executor = FakeExecutor()
            self.domain_runtime_state = None

        def run(self):
            return state

    class FakeUI:
        def select_mode(self):
            return False

        def display_message(self, _message):
            return None

        def approve_tool_call(self, **_kwargs):
            return False

        def confirm_flag(self, _candidate):
            return False

    monkeypatch.setattr(
        "agent.runtime.integration.build_runtime",
        lambda **_kwargs: FakeRuntime(),
    )
    question = manifest.to_question(
        experience_root=str(tmp_path / "experiences" / "challenges")
    )
    workflow = Workflow(
        {
            "checkpoint_dir": str(tmp_path / "checkpoints"),
            "platform": {},
        },
        FakeUI(),
        inputer=object(),
        submitter=object(),
    )

    assert workflow.solve(question) == "SOLVED"

    run = imported.experience.runs_dir / "run-001"
    assert (run / "checkpoint" / "run.json").is_file()
    assert (run / "checkpoint" / "intelligence.json").is_file()
    assert (run / "checkpoint" / "experiments.json").is_file()
    assert (run / "artifacts" / "manifest.json").is_file()
    assert "run-workflow-r85" in (run / "result.md").read_text(encoding="utf-8")
    assert "Persisted run status: `SOLVED`" in imported.experience.report_file.read_text(
        encoding="utf-8"
    )
    assert "## Challenge Description" in imported.experience.writeup_file.read_text(
        encoding="utf-8"
    )
    candidate_raw = json.loads(
        imported.experience.experience_candidates_file.read_text(encoding="utf-8")
    )
    assert candidate_raw["candidates"] == []
