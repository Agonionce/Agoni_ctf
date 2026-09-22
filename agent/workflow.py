"""解题流程编排模块。"""

import logging
from pathlib import Path
from typing import Callable, Optional

from ctf_platform.base import FlagSubmitter, Question, QuestionInputer
from ctf_platform.registry import create_inputer, create_submitter
from utils.user_interface import UserInterface

logger = logging.getLogger(__name__)

# 解题结束回调签名：(question, result) -> None
OnQuestionDone = Callable[[Question, str], None]


class Workflow:
    """负责衔接题目预处理、解题代理与 flag 提交流程。"""

    def __init__(
        self,
        config: dict,
        user_interface: UserInterface,
        inputer: Optional[QuestionInputer] = None,
        submitter: Optional[FlagSubmitter] = None,
        inputer_config: Optional[dict] = None,
        submitter_config: Optional[dict] = None,
    ) -> None:
        """初始化流程编排对象。

        Args:
            config: 全局配置字典。
            user_interface: 用户交互接口实现。
            inputer: 题目输入器。
            submitter: flag 提交器。
            inputer_config: 输入器配置（覆盖 config 中的 platform.inputer）。
            submitter_config: 提交器配置（覆盖 config 中的 platform.submitter）。

        Raises:
            ValueError: 当配置为空时抛出。
        """
        self.config = config
        self.user_interface = user_interface

        if self.config is None:
            raise ValueError("配置文件不存在")

        platform_config = config.get("platform", {})
        self.inputer = inputer or create_inputer(
            inputer_config or platform_config.get("inputer", {"type": "file"})
        )
        self.submitter = submitter or create_submitter(
            submitter_config or platform_config.get("submitter", {"type": "manual"}),
            user_interface=self.user_interface,
        )
        self.current_question: Optional[Question] = None
        self.on_question_done: Optional[OnQuestionDone] = None

    def solve(
        self,
        question: Question,
        resume_data: Optional[dict] = None,
    ) -> str:
        """执行单题解题流程。

        Args:
            question: 题目对象（含题目文本、靶机地址等完整信息）。
            resume_data: 可选存档恢复数据。

        Returns:
            解题结果字符串。
        """
        self.current_question = question
        resume_checkpoint = None
        if resume_data:
            from agent.intelligence.checkpoint import IntelligenceCheckpointData

            if isinstance(resume_data, IntelligenceCheckpointData):
                resume_checkpoint = resume_data
                self.user_interface.display_message(
                    "已恢复 RunState、IntelligenceState、Artifact 与 DomainRuntimeState"
                )
            else:
                self.user_interface.display_message(
                    "旧版 checkpoint 不含 R2 IntelligenceState，本次从新 Run 开始"
                )

        auto_mode = self.user_interface.select_mode()
        effective_config = dict(self.config)
        approval_resolver = None
        if auto_mode:
            execution_config = self.config.get("execution", {})
            execution_config = (
                dict(execution_config) if isinstance(execution_config, dict) else {}
            )
            execution_config["mode"] = "autonomous_local"
            effective_config["execution"] = execution_config
            self.user_interface.display_message(
                "R9.1 autonomous_local enabled: only explicitly permitted local Tools may run"
            )
        else:
            def resolve_approval(request: object) -> bool:
                return self.user_interface.approve_tool_call(
                    tool_name=request.tool_name,  # type: ignore[union-attr]
                    arguments=request.arguments,  # type: ignore[union-attr]
                    reason=request.reason,  # type: ignore[union-attr]
                    risk_level=request.risk_level,  # type: ignore[union-attr]
                )

            approval_resolver = resolve_approval

        from agent.challenge.experience import ChallengeExperienceManager
        from agent.challenge.models import ChallengeManifest
        from agent.runtime.integration import build_runtime

        runtime = build_runtime(
            question=question,
            config=effective_config,
            flag_confirmer=lambda candidate: self.confirm_flag(candidate.value),
            approval_resolver=approval_resolver,
            resume_checkpoint=resume_checkpoint,
        )
        self.agent = runtime
        challenge_experience = None
        challenge_run = None
        metadata = question.metadata if isinstance(question.metadata, dict) else {}
        raw_manifest = metadata.get("challenge_manifest")
        experience_root = metadata.get("challenge_experience_root")
        if isinstance(raw_manifest, dict) and isinstance(experience_root, str):
            manifest = ChallengeManifest.from_dict(raw_manifest)
            challenge_experience = ChallengeExperienceManager(experience_root)
            challenge_run = challenge_experience.start_run(manifest)
        state = runtime.run()
        if state.termination is not None and state.termination.flag_candidate:
            result = state.termination.flag_candidate.value
        elif state.termination is not None:
            result = f"{state.status.value}: {state.termination.message}"
        else:
            result = state.status.value
        checkpoint_path = None
        artifacts = []
        checkpoint_dir = self.config.get("checkpoint_dir", "./checkpoints")
        if isinstance(checkpoint_dir, str) and runtime.intelligence_store is not None:
            from agent.intelligence.checkpoint import IntelligenceCheckpoint

            artifacts = runtime.executor.artifacts_for_current_workspace() if hasattr(
                runtime.executor, "artifacts_for_current_workspace"
            ) else []
            checkpoint_path = Path(checkpoint_dir) / f"r4_{state.run_id}"
            IntelligenceCheckpoint(checkpoint_path).save(
                state,
                runtime.intelligence_store,
                artifacts,
                getattr(runtime, "domain_runtime_state", None),
            )
            self.user_interface.display_message(
                f"runtime checkpoint saved: {checkpoint_path}"
            )
        if (
            challenge_experience is not None
            and challenge_run is not None
            and runtime.intelligence_store is not None
        ):
            manifest = ChallengeManifest.from_dict(raw_manifest)
            workspace_manager = runtime.executor.workspace_manager
            workspace = workspace_manager.create(manifest.challenge_id)
            challenge_experience.complete_run(
                manifest,
                challenge_run,
                run_state=state,
                intelligence_state=runtime.intelligence_store.state,
                artifacts=artifacts,
                workspace=workspace,
                workspace_manager=workspace_manager,
                checkpoint_path=checkpoint_path,
                result=result,
            )
            self.user_interface.display_message(
                f"R8.5 challenge run bound: {challenge_run.root}"
            )
            try:
                from agent.completion.collector import ChallengeCompletionPipeline

                completion = ChallengeCompletionPipeline().complete(
                    manifest,
                    state,
                    runtime.intelligence_store.state,
                    artifacts,
                    experience_root=experience_root,
                )
                self.user_interface.display_message(
                    f"R8.6 challenge completion generated: {completion.report_path}"
                )
            except (OSError, ValueError) as error:
                self.user_interface.display_message(
                    f"R8.6 completion warning: {error}"
                )

        if self.on_question_done is not None:
            self.on_question_done(question, result)

        return result

    def confirm_flag(self, flag_candidate: str) -> bool:
        """通过提交器验证候选 flag。

        Args:
            flag_candidate: 候选 flag 字符串。

        Returns:
            验证成功返回 True，否则返回 False。
        """
        question = self.current_question
        if question is None:
            logger.warning("当前题目为空，无法提交flag")
            return False

        result = self.submitter.submit(flag_candidate, question)
        return result.success

    def summary_problem(self, problem: str) -> str:
        """对题目进行必要摘要。

        Args:
            problem: 原始题目描述。

        Returns:
            处理后的题目文本。
        """
        # R0 keeps the complete challenge text in ChallengeSpec. Summarization
        # is deferred until a typed context policy exists.
        return problem
