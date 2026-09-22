"""solve 子命令。"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from agent.challenge.experience import ChallengeExperienceManager
from agent.checkpoint import CheckpointManager
from cli.adapters.workflow_runner import (
    load_checkpoint_for_solve,
    resolve_question,
    run_workflow,
    setup_logging,
)
from cli.ui.interface import RichPromptToolkitInterface
from config import Config

def solve_command(
    challenge_id: Optional[str] = typer.Option(
        None,
        "--challenge",
        help="从 R8.5 ChallengeManifest 启动",
    ),
    challenge_root: str = typer.Option(
        "experiences/challenges",
        "--challenge-root",
        help="ChallengeManifest 目录",
    ),
    question_file: Optional[str] = typer.Option(
        None,
        "--question-file",
        help="从文件读取题目文本",
    ),
    question: Optional[str] = typer.Option(
        None,
        "--question",
        help="直接传入题目文本",
    ),
    auto: bool = typer.Option(
        False,
        "--auto",
        help="R9.1 autonomous_local 模式（仅限明确授权的本地能力）",
    ),
    manual: bool = typer.Option(
        False,
        "--manual",
        help="手动模式（等价于选择模式 2）",
    ),
    resume: bool = typer.Option(
        True,
        "--resume/--no-resume",
        help="是否尝试恢复存档",
    ),
    show_think: bool = typer.Option(
        True,
        "--show-think/--hide-think",
        help="是否显示手动审批中的思考摘要",
    ),
    plain: bool = typer.Option(
        False,
        "--plain",
        help="关闭彩色输出，回退为基础命令行交互",
    ),
) -> None:
    """启动解题流程（交互 / 非交互）。"""
    if auto and manual:
        raise typer.BadParameter("--auto 与 --manual 不能同时指定")
    selected_sources = sum(
        item is not None for item in (challenge_id, question_file, question)
    )
    if selected_sources > 1:
        raise typer.BadParameter(
            "--challenge、--question-file 与 --question 只能选择一个"
        )

    setup_logging()
    config = Config.load_config()

    forced_mode = None
    if auto:
        forced_mode = True
    if manual:
        forced_mode = False

    ui = RichPromptToolkitInterface(
        plain=plain,
        show_think=show_think,
        forced_auto_mode=forced_mode,
        forced_resume=resume if not resume else None,
    )

    checkpoint_dir_value = config.get("checkpoint_dir", "./checkpoints")
    checkpoint_dir = checkpoint_dir_value if isinstance(checkpoint_dir_value, str) else "./checkpoints"
    checkpoint_mgr = CheckpointManager(checkpoint_dir=checkpoint_dir)

    resume_data = load_checkpoint_for_solve(
        checkpoint_mgr=checkpoint_mgr,
        allow_resume=resume,
        ui=ui,
    )

    if challenge_id is not None:
        experience_manager = ChallengeExperienceManager(challenge_root)
        manifest = experience_manager.store.get(challenge_id)
        if manifest is None:
            raise typer.BadParameter(f"未知 Challenge ID: {challenge_id}")
        question_data = manifest.to_question(
            experience_root=str(experience_manager.root),
        )
        source = f"ChallengeManifest ({manifest.challenge_id})"
    else:
        _problem, question_data, source = resolve_question(
            config=config,
            question_text=question,
            question_file=question_file,
            user_interface=ui,
        )

    if isinstance(ui, RichPromptToolkitInterface):
        mode_text = "自动(参数指定)" if auto else "手动(参数指定)" if manual else "交互选择"
        ckpt_status = "将尝试恢复" if resume else "不恢复"
        ui.display_startup(
            mode_text=mode_text,
            question_source=source,
            checkpoint_status=ckpt_status,
        )

    try:
        result = run_workflow(
            config=config,
            user_interface=ui,
            question=question_data,
            resume_data=resume_data,
        )
    except KeyboardInterrupt:
        console = Console(no_color=plain, force_terminal=not plain)
        console.print("\n[yellow]已中断，进度已保存。[/yellow]")
        raise typer.Exit(0)
    except ModuleNotFoundError as error:
        raise typer.BadParameter(
            f"缺少运行依赖: {error.name}，请先执行 `pip install -r requirements.txt`"
        ) from error

    console = Console(no_color=plain, force_terminal=not plain)
    console.print(
        Panel(
            str(result),
            title="最终结果",
            border_style="green",
        )
    )
