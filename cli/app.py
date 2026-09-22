"""Typer 应用入口。"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

import typer

from cli.commands.checkpoint import app as checkpoint_app
from cli.commands.challenge import app as challenge_app
from cli.commands.benchmark import app as benchmark_app
from cli.commands.config_cmd import app as config_app
from cli.commands.domain import app as domain_app
from cli.commands.domain_runtime import app as domain_runtime_app
from cli.commands.experiment import evidence_app, experiment_app, hypothesis_app
from cli.commands.experience import app as experience_app
from cli.commands.intelligence import app as intelligence_app
from cli.commands.mcp import app as mcp_app
from cli.commands.policy import app as policy_app
from cli.commands.resume import resume_command
from cli.commands.sandbox import app as sandbox_app
from cli.commands.skill import app as skill_app
from cli.commands.solve import solve_command
from cli.commands.tools import app as tools_app
from cli.commands.ui import app as ui_app
from cli.commands.web import app as web_app

app = typer.Typer(
    name="agonionce",
    help="Agonionce CTF Agent 命令行工具",
    no_args_is_help=True,
)

# 注册核心命令
app.command("solve")(solve_command)
app.command("resume")(resume_command)
app.add_typer(challenge_app, name="challenge")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(checkpoint_app, name="checkpoint")
app.add_typer(config_app, name="config")
app.add_typer(domain_app, name="domain")
app.add_typer(intelligence_app, name="intelligence")
app.add_typer(mcp_app, name="mcp")
app.add_typer(policy_app, name="policy")
app.add_typer(domain_runtime_app, name="runtime")
app.add_typer(skill_app, name="skill")
app.add_typer(tools_app, name="tools")
app.add_typer(ui_app, name="ui")
app.add_typer(web_app, name="web")
app.add_typer(experiment_app, name="experiment")
app.add_typer(hypothesis_app, name="hypothesis")
app.add_typer(evidence_app, name="evidence")
app.add_typer(experience_app, name="experience")
app.add_typer(sandbox_app, name="sandbox")

# 自动发现平台 CLI 命令模块（定义了 register 函数的模块）
_commands_dir = Path(__file__).parent / "commands"
for _module_info in pkgutil.iter_modules([str(_commands_dir)]):
    _module = importlib.import_module(f"cli.commands.{_module_info.name}")
    _register_fn = getattr(_module, "register", None)
    if callable(_register_fn):
        _register_fn(app)


def run() -> None:
    """运行 CLI 应用。"""
    app()


if __name__ == "__main__":
    run()
