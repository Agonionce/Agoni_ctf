import json

from typer.testing import CliRunner

from agent.domains.manager import build_default_runtime_manager
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import ChallengeSpec, RunState
from cli.app import app


runner = CliRunner()


def test_runtime_list_cli():
    result = runner.invoke(app, ["runtime", "list"])

    assert result.exit_code == 0
    assert "Available Domain Runtimes" in result.stdout
    assert "RECON" in result.stdout
    assert "CLASSIFICATION" in result.stdout


def test_runtime_current_cli_without_checkpoint(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["runtime", "current"])

    assert result.exit_code == 0
    assert "尚无活动 checkpoint" in result.stdout


def test_runtime_current_cli_restores_persisted_phase(monkeypatch, tmp_path):
    checkpoint_root = tmp_path / "checkpoints"
    challenge = ChallengeSpec("r4-cli", "PHP Login", "cookie SQL", category="web")
    manager = build_default_runtime_manager()
    state = manager.initialize("web", challenge)
    manager.next_phase()
    IntelligenceCheckpoint(checkpoint_root / "r4_cli").save(
        RunState(challenge),
        IntelligenceStore.create(challenge.challenge_id),
        [],
        state,
    )
    (tmp_path / "config.json").write_text(
        json.dumps({"checkpoint_dir": str(checkpoint_root)}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["runtime", "current"])

    assert result.exit_code == 0
    assert "Runtime: web" in result.stdout
    assert "Phase: ANALYSIS" in result.stdout
    assert "Source: checkpoint" in result.stdout
