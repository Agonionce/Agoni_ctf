"""Runtime-owned supervision for the loopback R14 workbench.

The coordinator exposes deliberately small, challenge-local operator state. It never
executes a Tool itself: ``AgentRuntime`` still reaches every action through
``ToolRuntime``, ``PolicyEngine`` and ``ApprovalManager``.
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from agent.challenge.experience import (
    ChallengeExperienceManager,
    ChallengeRunBinding,
)
from agent.challenge.models import ChallengeManifest
from agent.completion.collector import ChallengeCompletionPipeline
from agent.intelligence.checkpoint import (
    IntelligenceCheckpoint,
    IntelligenceCheckpointData,
)
from agent.policy.approval import ApprovalRequest
from agent.runtime.contracts import (
    RunState,
    RunStatus,
    TerminationDecision,
    TerminationReason,
)
from agent.runtime.integration import build_runtime


RuntimeFactory = Callable[..., Any]
ConfigProvider = Callable[[], Mapping[str, Any]]


STATUS_LABELS = {
    "CREATED": "未开始",
    "RUNNING": "分析中",
    "WAITING": "等待确认",
    "SOLVED": "已完成",
    "BLOCKED": "需要帮助",
    "FAILED": "未解决",
    "BUDGET_EXHAUSTED": "已到本轮上限",
    "ABORTED": "已安全停止",
    "PAUSED": "已暂停",
}

RESUMABLE_STATUSES = frozenset(
    {"BLOCKED", "FAILED", "BUDGET_EXHAUSTED", "ABORTED", "PAUSED"}
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RunMilestone:
    """One concise user-facing outcome, never an execution trace."""

    title: str
    detail: str
    state: str
    occurred_at: str = field(default_factory=utc_now_iso)


@dataclass
class PendingRunDecision:
    """A blocking human decision exposed to the local authorized operator."""

    decision_id: str
    kind: str
    title: str
    summary: str
    risk_label: str
    created_at: str = field(default_factory=utc_now_iso)
    approved: bool | None = None
    candidate_value: str | None = None
    candidate_source: str | None = None
    candidate_evidence: str | None = None
    event: threading.Event = field(default_factory=threading.Event, repr=False)


@dataclass(frozen=True)
class SupervisedRunView:
    status: str
    status_label: str
    active: bool
    milestones: tuple[RunMilestone, ...]
    pending_decision: PendingRunDecision | None
    can_start: bool
    can_abort: bool
    can_resume: bool
    completion_available: bool


@dataclass
class _RunSession:
    manifest: ChallengeManifest
    binding: ChallengeRunBinding
    runtime: Any
    milestones: list[RunMilestone]
    thread: threading.Thread | None = None
    pending: PendingRunDecision | None = None
    active: bool = True
    status: str = "RUNNING"
    completion_available: bool = False
    error_message: str = ""
    abort_requested: bool = False


class SupervisedRunCoordinator:
    """Coordinate supervised AgentRuntime runs without creating Tool authority."""

    def __init__(
        self,
        *,
        workspace_root: str | Path = "workspace",
        challenge_root: str | Path = "experiences/challenges",
        checkpoint_root: str | Path = ".runtime/webui-runs",
        global_experience_path: str | Path = "experiences/global/experience.json",
        config_provider: ConfigProvider | None = None,
        runtime_factory: RuntimeFactory = build_runtime,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.manager = ChallengeExperienceManager(Path(challenge_root).resolve())
        self.checkpoint_root = Path(checkpoint_root).resolve()
        self.global_experience_path = Path(global_experience_path).resolve()
        self._config_provider = config_provider or self._default_config
        self._runtime_factory = runtime_factory
        self._sessions: dict[str, _RunSession] = {}
        self._starting: set[str] = set()
        self._lock = threading.RLock()

    def start(self, challenge_id: str, *, resume: bool = False) -> SupervisedRunView:
        manifest = self._manifest(challenge_id)
        with self._lock:
            current = self._sessions.get(challenge_id)
            if challenge_id in self._starting or (current is not None and current.active):
                raise ValueError("该题正在分析中")
            self._starting.add(challenge_id)

        session: _RunSession | None = None
        try:
            resume_checkpoint = self._load_resume_checkpoint(manifest) if resume else None
            config = self._runtime_config(challenge_id)
            question = manifest.to_question(experience_root=str(self.manager.root))

            session_holder: dict[str, _RunSession] = {}

            def resolve_approval(request: ApprovalRequest) -> bool:
                return self._wait_for_approval(session_holder["session"], request)

            def confirm_candidate(candidate: object) -> bool:
                return self._wait_for_candidate_confirmation(
                    session_holder["session"], candidate
                )

            runtime = self._runtime_factory(
                question=question,
                config=config,
                flag_confirmer=confirm_candidate,
                approval_resolver=resolve_approval,
                resume_checkpoint=resume_checkpoint,
            )
            binding = self.manager.start_run(manifest)
            milestones = [
                RunMilestone(
                    title="已恢复上次进度" if resume else "分析已开始",
                    detail=(
                        "已从安全存档继续，新的阶段成果会显示在这里。"
                        if resume
                        else "已启用本题授权范围内的自动运行，阶段成果会显示在这里。"
                    ),
                    state="current",
                )
            ]
            session = _RunSession(
                manifest=manifest,
                binding=binding,
                runtime=runtime,
                milestones=milestones,
            )
            session_holder["session"] = session
            thread = threading.Thread(
                target=self._run,
                args=(session,),
                name=f"agonionce-ui-{challenge_id}",
                daemon=True,
            )
            session.thread = thread
            with self._lock:
                self._sessions[challenge_id] = session
                self._starting.discard(challenge_id)
            thread.start()
            return self.view(challenge_id)
        except Exception:
            with self._lock:
                self._starting.discard(challenge_id)
                if session is not None and self._sessions.get(challenge_id) is session:
                    self._sessions.pop(challenge_id, None)
            raise

    def view(self, challenge_id: str) -> SupervisedRunView:
        manifest = self._manifest(challenge_id)
        with self._lock:
            session = self._sessions.get(challenge_id)
            if session is not None:
                return self._session_view(session)
            if challenge_id in self._starting:
                return SupervisedRunView(
                    status="RUNNING",
                    status_label=STATUS_LABELS["RUNNING"],
                    active=True,
                    milestones=(
                        RunMilestone(
                            title="正在准备分析",
                            detail="正在建立受控运行环境。",
                            state="current",
                        ),
                    ),
                    pending_decision=None,
                    can_start=False,
                    can_abort=False,
                    can_resume=False,
                    completion_available=False,
                )
        return self._persisted_view(manifest)

    def decide(
        self,
        challenge_id: str,
        decision_id: str,
        *,
        approved: bool,
    ) -> SupervisedRunView:
        with self._lock:
            session = self._sessions.get(challenge_id)
            if session is None or not session.active or session.pending is None:
                raise ValueError("当前没有等待确认的操作")
            pending = session.pending
            if pending.decision_id != decision_id:
                raise ValueError("确认项已经变化，请刷新后重试")
            if pending.approved is not None:
                raise ValueError("该确认项已经处理")
            pending.approved = approved
            pending.event.set()
            session.pending = None
            session.status = "RUNNING"
            self._append_milestone(
                session,
                "已允许继续" if approved else "已拒绝本次操作",
                (
                    "分析会在原有授权范围内继续。"
                    if approved
                    else "该操作不会执行，分析会根据现有证据调整。"
                ),
                "done",
            )
        return self.view(challenge_id)

    def abort(self, challenge_id: str) -> SupervisedRunView:
        with self._lock:
            session = self._sessions.get(challenge_id)
            if session is None or not session.active:
                raise ValueError("当前没有正在进行的分析")
            session.abort_requested = True
            session.runtime.request_abort()
            if session.pending is not None:
                session.pending.approved = False
                session.pending.event.set()
                session.pending = None
            session.status = "RUNNING"
            self._append_milestone(
                session,
                "正在安全停止",
                "会在当前受控边界完成后保存进度。",
                "current",
            )
        return self.view(challenge_id)

    def _run(self, session: _RunSession) -> None:
        runtime = session.runtime
        try:
            state = runtime.run()
        except Exception:
            state = runtime.state
            state.set_termination(
                TerminationDecision(
                    status=RunStatus.FAILED,
                    reason=TerminationReason.FATAL_ERROR,
                    message="supervised runtime failed",
                )
            )
            finalize = getattr(runtime.checkpoint_handler, "finalize", None)
            if callable(finalize):
                try:
                    finalize(state)
                except (OSError, ValueError):
                    pass
            session.error_message = "分析未能继续，已保留可恢复的进度。"

        completion_available = False
        try:
            self._bind_completed_run(session, state)
            completion_available = True
        except (OSError, ValueError, RuntimeError):
            session.error_message = session.error_message or "结果整理未完成，可以稍后重试。"

        with self._lock:
            session.active = False
            session.pending = None
            session.status = state.status.value
            session.completion_available = completion_available
            title, detail = self._final_milestone(state.status.value, session.error_message)
            self._append_milestone(session, title, detail, "done")
            session.runtime = None

    def _bind_completed_run(self, session: _RunSession, state: RunState) -> None:
        runtime = session.runtime
        intelligence_store = getattr(runtime, "intelligence_store", None)
        executor = getattr(runtime, "executor", None)
        if intelligence_store is None or executor is None:
            raise RuntimeError("runtime completion state is unavailable")
        artifacts = (
            executor.artifacts_for_current_workspace()
            if hasattr(executor, "artifacts_for_current_workspace")
            else []
        )
        checkpoint_handler = getattr(runtime, "checkpoint_handler", None)
        checkpoint_path = None
        if checkpoint_handler is not None:
            checkpoint = getattr(checkpoint_handler, "checkpoint", None)
            checkpoint_path = getattr(checkpoint, "directory", None)
        workspace_manager = executor.workspace_manager
        workspace = workspace_manager.create(session.manifest.challenge_id)
        self.manager.complete_run(
            session.manifest,
            session.binding,
            run_state=state,
            intelligence_state=intelligence_store.state,
            artifacts=artifacts,
            workspace=workspace,
            workspace_manager=workspace_manager,
            checkpoint_path=checkpoint_path,
            result=self._safe_result(state.status.value),
        )
        ChallengeCompletionPipeline().complete(
            session.manifest,
            state,
            intelligence_store.state,
            artifacts,
            experience_root=self.manager.root,
        )

    def _wait_for_approval(
        self,
        session: _RunSession,
        request: ApprovalRequest,
    ) -> bool:
        """Apply the run's explicit local pre-authorization without blocking."""

        with self._lock:
            return not session.abort_requested

    def _wait_for_candidate_confirmation(self, session: _RunSession, candidate: object) -> bool:
        """Accept the strongest candidate under the run's explicit authorization."""

        with self._lock:
            return not session.abort_requested

    def _session_view(self, session: _RunSession) -> SupervisedRunView:
        status = "WAITING" if session.pending is not None else session.status
        return SupervisedRunView(
            status=status,
            status_label=STATUS_LABELS.get(status, "需要帮助"),
            active=session.active,
            milestones=tuple(session.milestones),
            pending_decision=session.pending,
            can_start=not session.active,
            can_abort=session.active,
            can_resume=(
                not session.active
                and status in RESUMABLE_STATUSES
                and self._has_resume_checkpoint(session.manifest)
            ),
            completion_available=session.completion_available,
        )

    def _persisted_view(self, manifest: ChallengeManifest) -> SupervisedRunView:
        latest = self._latest_completed_run(manifest)
        if latest is None:
            return SupervisedRunView(
                status="CREATED",
                status_label=STATUS_LABELS["CREATED"],
                active=False,
                milestones=(),
                pending_decision=None,
                can_start=True,
                can_abort=False,
                can_resume=False,
                completion_available=False,
            )
        try:
            state = IntelligenceCheckpoint(latest / "checkpoint").load().run_state
            status = state.status.value
        except (OSError, ValueError):
            status = "FAILED"
        title, detail = self._final_milestone(status, "")
        return SupervisedRunView(
            status=status,
            status_label=STATUS_LABELS.get(status, "需要帮助"),
            active=False,
            milestones=(RunMilestone(title=title, detail=detail, state="done"),),
            pending_decision=None,
            can_start=True,
            can_abort=False,
            can_resume=(status in RESUMABLE_STATUSES and self._has_resume_checkpoint(manifest)),
            completion_available=(latest / "run.json").is_file(),
        )

    def _load_resume_checkpoint(
        self,
        manifest: ChallengeManifest,
    ) -> IntelligenceCheckpointData:
        latest = self._latest_completed_run(manifest)
        if latest is None:
            raise ValueError("没有可恢复的安全存档")
        checkpoint = IntelligenceCheckpoint(latest / "checkpoint").load()
        if checkpoint.run_state.challenge.challenge_id != manifest.challenge_id:
            raise ValueError("存档不属于该题目")
        if checkpoint.run_state.status.value not in RESUMABLE_STATUSES:
            raise ValueError("当前结果不需要恢复")
        checkpoint.run_state.fork_for_resume()
        if checkpoint.step_checkpoint is not None:
            checkpoint.step_checkpoint.run_id = checkpoint.run_state.run_id
        if checkpoint.experiment_runtime_state is not None:
            checkpoint.experiment_runtime_state.rebind_run(checkpoint.run_state.run_id)
        checkpoint.checkpoint_directory = None
        return checkpoint

    def _has_resume_checkpoint(self, manifest: ChallengeManifest) -> bool:
        latest = self._latest_completed_run(manifest)
        if latest is None:
            return False
        checkpoint = latest / "checkpoint"
        return all(
            (checkpoint / name).is_file()
            for name in ("run.json", "intelligence.json", "artifacts.json")
        )

    def _latest_completed_run(self, manifest: ChallengeManifest) -> Path | None:
        paths = self.manager.paths_for(manifest)
        candidates = [
            item
            for item in paths.runs_dir.glob("run-*")
            if item.is_dir() and (item / "run.json").is_file()
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: int(item.name.rsplit("-", 1)[-1]))

    def _manifest(self, challenge_id: str) -> ChallengeManifest:
        manifest = self.manager.store.get(challenge_id)
        if manifest is None:
            raise ValueError("未找到该题目")
        return manifest

    def _runtime_config(self, challenge_id: str) -> dict[str, Any]:
        config = copy.deepcopy(dict(self._config_provider()))
        execution = config.get("execution")
        execution = dict(execution) if isinstance(execution, Mapping) else {}
        execution.update(
            {
                "mode": "supervised",
                "workspace_root": str(self.workspace_root),
                "default_policy": "safe",
            }
        )
        config["execution"] = execution
        config["checkpoint_dir"] = str(self.checkpoint_root / challenge_id)
        experience = config.get("experience")
        experience = dict(experience) if isinstance(experience, Mapping) else {}
        experience["path"] = str(self.global_experience_path)
        config["experience"] = experience
        return config

    @staticmethod
    def _default_config() -> Mapping[str, Any]:
        from config import Config

        return Config.load_config()

    @staticmethod
    def _approval_copy(tool_name: str, arguments: Mapping[str, Any]) -> tuple[str, str]:
        labels = {
            "file": ("查看文件信息", "读取已导入材料的基本信息。"),
            "workspace_list": ("查看题目材料", "列出当前题目工作区中的文件名。"),
            "workspace_read_text": ("读取文本材料", "读取一份已导入的文本材料。"),
            "workspace_read_bytes": ("读取二进制材料", "读取一份已导入材料的有限字节。"),
            "workspace_write_text": ("保存分析材料", "把阶段分析保存到当前题目工作区。"),
            "file_hash": ("核对材料指纹", "计算一份题目材料的校验摘要。"),
            "archive_list": ("查看压缩包目录", "只查看压缩包内的文件清单，不执行其中内容。"),
            "sandbox_python": ("运行隔离分析", "在受控沙箱中处理当前题目的本地材料。"),
            "python": ("运行受控分析", "在题目工作区内执行一次受控分析。"),
            "bash": ("运行本地分析", "在题目工作区内执行一次受控命令。"),
            "web_intelligence": ("整理网页结构", "分析已经保存的本地响应材料。"),
        }
        if tool_name == "http_request":
            raw_url = str(arguments.get("url", ""))
            parsed = urlsplit(raw_url)
            method = str(arguments.get("method", "GET")).upper()
            path = SupervisedRunCoordinator._safe_request_path(parsed.path or "/")
            return "访问已授权目标", f"向已声明的本地目标发送 {method} {path}。"
        return labels.get(tool_name, ("执行受控操作", "在当前题目的授权范围内继续分析。"))

    @staticmethod
    def _safe_request_path(value: str) -> str:
        """Keep the complete local request path in operator-facing milestones."""

        return str(value)

    @staticmethod
    def _risk_label(value: str) -> str:
        return {
            "LOW": "低风险",
            "MEDIUM": "需留意",
            "HIGH": "高风险",
            "CRITICAL": "关键操作",
        }.get(str(value).upper(), "需要确认")

    @staticmethod
    def _safe_result(status: str) -> str:
        return {
            "SOLVED": "本轮已完成，并保留了证据绑定的结果。",
            "ABORTED": "本轮已按用户请求安全停止。",
            "BLOCKED": "本轮需要新的信息或用户协助。",
            "BUDGET_EXHAUSTED": "本轮已到受控分析上限。",
            "FAILED": "本轮未形成可继续的结果。",
        }.get(status, "本轮分析已结束。")

    @classmethod
    def _final_milestone(cls, status: str, error_message: str) -> tuple[str, str]:
        if error_message:
            return "本轮已结束", error_message
        return {
            "SOLVED": ("题目已完成", "报告与解题记录已整理，可以进入报告页查看。"),
            "ABORTED": ("已安全停止", "当前进度已保存，之后可以从存档继续。"),
            "BLOCKED": ("需要你的帮助", "现有证据不足以继续，可以补充材料后再恢复。"),
            "BUDGET_EXHAUSTED": ("本轮分析已结束", "阶段成果已保存，可以从存档继续。"),
            "FAILED": ("本轮未解决", "已保留阶段成果，可以调整题目材料后继续。"),
        }.get(status, ("本轮分析已结束", "阶段成果已保存。"))

    @staticmethod
    def _append_milestone(
        session: _RunSession,
        title: str,
        detail: str,
        state: str,
    ) -> None:
        session.milestones.append(RunMilestone(title=title, detail=detail, state=state))
        if len(session.milestones) > 20:
            session.milestones[:] = session.milestones[-20:]
