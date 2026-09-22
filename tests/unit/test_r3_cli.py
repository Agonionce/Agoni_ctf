from typer.testing import CliRunner

from cli.app import app


runner = CliRunner()


def test_domain_list_cli():
    result = runner.invoke(app, ["domain", "list"])

    assert result.exit_code == 0
    assert "Available Domains" in result.stdout
    assert "web" in result.stdout
    assert "misc" in result.stdout


def test_skill_list_cli():
    result = runner.invoke(app, ["skill", "list"])

    assert result.exit_code == 0
    assert "Available Skills" in result.stdout
    assert "sql_injection" in result.stdout
    assert "binary_triage" in result.stdout


def test_skill_current_cli_without_checkpoint(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["skill", "current"])

    assert result.exit_code == 0
    assert "尚无活动 checkpoint" in result.stdout
