"""R14 loopback-only local UI command."""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel

from webui.app import create_app
from webui.service import UISettings


app = typer.Typer(help="R14 本地题目工作台")


@app.command("start")
def start_ui(
    port: int = typer.Option(8787, min=1024, max=65535, help="本地监听端口"),
    open_browser: bool = typer.Option(
        True,
        "--open-browser/--no-open-browser",
        help="启动后打开浏览器",
    ),
    workspace_root: Path = typer.Option(Path("workspace"), help="隔离工作区根目录"),
    experience_root: Path = typer.Option(
        Path("experiences/challenges"),
        help="私有题目记录根目录",
    ),
) -> None:
    """Start the local challenge workbench on loopback only."""

    frontend = Path(__file__).resolve().parents[2] / "webui" / "frontend" / "dist"
    if not frontend.is_dir():
        raise typer.BadParameter(
            "前端尚未构建，请先在 webui/frontend 执行 npm install && npm run build"
        )
    url = f"http://127.0.0.1:{port}"
    Console().print(
        Panel(
            f"地址: {url}\n范围: 仅本机\n按 Ctrl+C 停止",
            title="Agonionce 本地题目工作台",
            border_style="blue",
        )
    )
    if open_browser:
        timer = threading.Timer(0.8, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    uvicorn.run(
        create_app(
            UISettings(
                workspace_root=workspace_root,
                experience_root=experience_root,
            )
        ),
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
