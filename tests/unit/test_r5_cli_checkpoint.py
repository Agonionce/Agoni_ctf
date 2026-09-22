import json

from typer.testing import CliRunner

from agent.domains.manager import build_default_runtime_manager
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import ChallengeSpec, RunState
from cli.app import app


runner = CliRunner()


def test_web_status_cli_without_checkpoint(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["web", "status"])

    assert result.exit_code == 0
    assert "尚无活动 checkpoint" in result.stdout


def test_web_state_checkpoint_and_cli_mask_cookie_values(monkeypatch, tmp_path):
    checkpoint_root = tmp_path / "checkpoints"
    challenge = ChallengeSpec(
        "r5-cli",
        "Local Login",
        "authorized local web challenge",
        category="web",
        metadata={"base_url": "http://127.0.0.1:8000"},
    )
    manager = build_default_runtime_manager()
    state = manager.initialize("web", challenge)
    assert isinstance(state, WebRuntimeState)
    state.record_endpoint("/login")
    state.record_parameter("username", "/login")
    state.cookies["session"] = "local-secret-cookie"
    state.record_technology("FakePHP/1.0")
    IntelligenceCheckpoint(checkpoint_root / "r5_cli").save(
        RunState(challenge),
        IntelligenceStore.create(challenge.challenge_id),
        [],
        state,
    )
    restored = IntelligenceCheckpoint(checkpoint_root / "r5_cli").load()
    assert isinstance(restored.domain_runtime_state, WebRuntimeState)
    assert restored.domain_runtime_state.cookies["session"] == "local-secret-cookie"
    (tmp_path / "config.json").write_text(
        json.dumps({"checkpoint_dir": str(checkpoint_root)}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["web", "status"])

    assert result.exit_code == 0
    assert "Web Runtime Status" in result.stdout
    assert "/login" in result.stdout
    assert "username" in result.stdout
    assert "session" in result.stdout
    assert "local-secret-cookie" not in result.stdout
