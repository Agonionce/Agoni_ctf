"""Compatibility bridge from the CLI stack to the R0 + R1 runtime boundary."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Dict

from agent.domains.context import SkillContextBuilder
from agent.domains.integration import DomainRuntimeAnalyzer
from agent.domains.loader import SkillLoader
from agent.domains.manager import build_default_runtime_manager
from agent.domains.router import SkillRouter
from agent.domains.runtime_context import DomainRuntimeContextBuilder
from agent.domains.web.analyzer import WebIntelligenceAnalyzer
from agent.domains.web.intelligence.context import WebAttackSurfaceContextBuilder
from agent.domains.web.research.context import WebResearchContextBuilder
from agent.domains.web.research.manager import WebResearchManager
from agent.domains.web.research.session import WebSessionManager
from agent.domains.web.state import WebRuntimeState
from agent.experience.retriever import ExperienceRetriever
from agent.experience.quality import ExperienceQualityStore
from agent.experience.store import ExperienceStore
from agent.intelligence.checkpoint import (
    IntelligenceCheckpoint,
    IntelligenceCheckpointData,
    RuntimeStepCheckpoint,
)
from agent.intelligence.experiment.context import ExperimentContextBuilder
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentRuntimeState,
)
from agent.intelligence.experiment.runtime.loop import AutonomousExperimentLoop
from agent.intelligence.experiment.runtime.orchestrator import ExperimentOrchestrator
from agent.intelligence.retriever import IntelligenceRetriever
from agent.intelligence.store import IntelligenceStore
from agent.mcp.client import MCPClientManager
from agent.mcp.registry import MCPServerRegistry
from agent.policy.approval import ApprovalManager, ApprovalRequest
from agent.policy.engine import PolicyEngine
from agent.runtime.analyzer import JsonAnalyzer
from agent.runtime.contracts import ChallengeSpec, RunBudget
from agent.runtime.planner import JsonPlanner
from agent.runtime.runtime import AgentRuntime
from agent.tools.registry import build_default_registry
from agent.tools.runtime import ToolRuntime, ToolRuntimeExecutor
from agent.tools.settings import ExecutionSettings
from agent.workspace.manager import WorkspaceManager
from ctf_platform.base import Question
from utils.llm_request import LLMRequest


class OpenAIJsonRequester:
    """Adapt the existing OpenAI-compatible client to the R0 JSON boundary."""

    def __init__(self) -> None:
        self.client = LLMRequest("planner")

    def __call__(self, system_prompt: str, user_prompt: str) -> Any:
        return self.client.text_completion(
            user_prompt,
            json_check=True,
            system_prompt=system_prompt,
        )


def challenge_from_question(question: Question) -> ChallengeSpec:
    challenge_id = "challenge-" + hashlib.sha256(
        question.content.encode("utf-8")
    ).hexdigest()[:16]
    metadata = dict(question.metadata) if isinstance(question.metadata, dict) else {}
    if question.url and "base_url" not in metadata:
        metadata["base_url"] = question.url
    return ChallengeSpec(
        challenge_id=str(metadata.get("challenge_id", challenge_id)),
        title=question.title or "Untitled challenge",
        description=question.content,
        category=metadata.get("category"),
        authorization_scope=str(
            metadata.get("authorization_scope", "authorized_ctf_only")
        ),
        metadata=metadata,
    )


def build_runtime(
    question: Question,
    config: Dict[str, Any],
    flag_confirmer: Callable[[object], bool] | None = None,
    approval_resolver: Callable[[ApprovalRequest], bool] | None = None,
    resume_checkpoint: IntelligenceCheckpointData | None = None,
) -> AgentRuntime:
    """Build R0 orchestration over R1's policy-controlled ToolRuntime.

    Missing ``execution`` configuration deliberately falls back to manual,
    workspace-scoped execution. The Planner sees schemas from ToolRegistry;
    it never receives an executor-specific shell shortcut.
    """

    challenge = challenge_from_question(question)
    if (
        resume_checkpoint is not None
        and resume_checkpoint.run_state.challenge.challenge_id != challenge.challenge_id
    ):
        raise ValueError("R2 checkpoint belongs to a different challenge")
    execution = ExecutionSettings.from_mapping(config.get("execution"))
    mcp_server_registry = MCPServerRegistry.from_config(config.get("mcp"))
    mcp_client_manager = MCPClientManager(mcp_server_registry)
    registry = build_default_registry(mcp_manager=mcp_client_manager)
    requester = OpenAIJsonRequester()
    runtime_config = config.get("runtime")
    if isinstance(runtime_config, dict):
        budget_config = dict(runtime_config)
        runtime_default_domain = str(
            budget_config.pop("default_domain", "auto") or "auto"
        ).lower()
        budget = RunBudget.from_mapping(budget_config)
    else:
        runtime_default_domain = "auto"
        budget = RunBudget.from_mapping(runtime_config)
    intelligence_store = (
        resume_checkpoint.intelligence_store
        if resume_checkpoint is not None
        else IntelligenceStore.create(challenge.challenge_id)
    )
    retriever = IntelligenceRetriever(intelligence_store)
    experiment_context_builder = ExperimentContextBuilder(intelligence_store)
    experience_config = config.get("experience")
    if isinstance(experience_config, dict):
        experience_path = experience_config.get(
            "path",
            "./experiences/experience.json",
        )
        experience_limit = experience_config.get("max_context_items", 5)
    else:
        experience_path = "./experiences/experience.json"
        experience_limit = 5
    if not isinstance(experience_path, str) or not experience_path.strip():
        raise ValueError("experience.path must be a non-empty string")
    if (
        not isinstance(experience_limit, int)
        or isinstance(experience_limit, bool)
        or experience_limit <= 0
    ):
        raise ValueError("experience.max_context_items must be an integer > 0")
    experience_store = ExperienceStore(experience_path)
    experience_retriever = ExperienceRetriever(
        experience_store,
        ExperienceQualityStore.for_experience_path(experience_path),
    )
    skill_config = config.get("skills")
    extra_skill_paths = (
        skill_config.get("paths", []) if isinstance(skill_config, dict) else []
    )
    if not isinstance(extra_skill_paths, list):
        extra_skill_paths = []
    domain_config = config.get("domain")
    default_domain = (
        domain_config.get("default", "auto")
        if isinstance(domain_config, dict)
        else "auto"
    )
    skill_loader = SkillLoader(extra_paths=extra_skill_paths)
    domain_router = SkillRouter(
        loader=skill_loader,
        default_domain=str(default_domain),
    )
    artifact_metadata = resume_checkpoint.artifacts if resume_checkpoint is not None else ()
    domain_selection = domain_router.route(challenge, artifact_metadata)
    context_builder = SkillContextBuilder()
    domain_runtime_manager = build_default_runtime_manager()
    restored_domain_state = (
        resume_checkpoint.domain_runtime_state
        if resume_checkpoint is not None
        else None
    )
    selected_runtime_domain = (
        restored_domain_state.domain
        if restored_domain_state is not None
        else (
            domain_selection.primary_domain
            if runtime_default_domain == "auto"
            else runtime_default_domain
        )
    )
    domain_runtime_state = domain_runtime_manager.initialize(
        selected_runtime_domain,
        challenge,
        restored_domain_state,
    )
    runtime_context_builder = DomainRuntimeContextBuilder()
    web_surface_context_builder = WebAttackSurfaceContextBuilder()
    web_research_context_builder = WebResearchContextBuilder()
    web_session_manager = None
    web_research_manager = None
    if isinstance(domain_runtime_state, WebRuntimeState):
        web_session_manager = WebSessionManager(domain_runtime_state.sessions)
        if domain_runtime_state.base_url and not domain_runtime_state.sessions:
            web_session_manager.create(
                domain_runtime_state.base_url,
                session_id="default",
            )
        web_research_manager = WebResearchManager(domain_runtime_state)
        http_tool = registry.get("http_request")
        bind_session_manager = getattr(http_tool, "bind_session_manager", None)
        if callable(bind_session_manager):
            bind_session_manager(web_session_manager)

    def intelligence_context(current_challenge: ChallengeSpec, state: object) -> Dict[str, Any]:
        last_analysis = getattr(state, "last_analysis", None)
        recent_summary = getattr(last_analysis, "summary", "") if last_analysis else ""
        category = current_challenge.category or ""
        query = " ".join(
            [current_challenge.title, current_challenge.description, recent_summary]
        )
        return retriever.retrieve(
            query,
            categories=[category] if category else (),
        ).to_dict()

    def domain_context(current_challenge: ChallengeSpec, state: object) -> Dict[str, Any]:
        return context_builder.build(
            current_challenge,
            domain_selection,
            skill_loader.all(),
            intelligence_context(current_challenge, state),
        )

    def domain_runtime_context(
        current_challenge: ChallengeSpec,
        state: object,
    ) -> Dict[str, Any]:
        selected_runtime, current_domain_state = domain_runtime_manager.current()
        current_intelligence = intelligence_context(current_challenge, state)
        current_skill_context = context_builder.build(
            current_challenge,
            domain_selection,
            skill_loader.all(),
            current_intelligence,
        )
        return runtime_context_builder.build(
            current_challenge,
            selected_runtime,
            current_domain_state,
            current_skill_context,
            current_intelligence,
        )

    def experiment_context(
        _current_challenge: ChallengeSpec,
        _state: object,
    ) -> Dict[str, Any]:
        return experiment_context_builder.build(experiment_runtime_state)

    def experience_context(
        current_challenge: ChallengeSpec,
        _state: object,
    ) -> Dict[str, Any]:
        return experience_retriever.retrieve(
            current_challenge,
            domain=domain_selection.primary_domain,
            skills=domain_selection.selected_skills,
            artifact_metadata=artifact_metadata,
            limit=experience_limit,
        ).to_dict()

    def web_attack_surface_context(
        _current_challenge: ChallengeSpec,
        _state: object,
    ) -> Dict[str, Any]:
        _runtime, current_domain_state = domain_runtime_manager.current()
        if not isinstance(current_domain_state, WebRuntimeState):
            return {}
        return web_surface_context_builder.build(
            current_domain_state.web_intelligence.attack_surface
        )

    def web_research_context(
        current_challenge: ChallengeSpec,
        state: object,
    ) -> Dict[str, Any]:
        _runtime, current_domain_state = domain_runtime_manager.current()
        if not isinstance(current_domain_state, WebRuntimeState):
            return {}
        return web_research_context_builder.build(
            current_domain_state,
            intelligence=intelligence_context(current_challenge, state),
            previous_experiments=experiment_runtime_state.records,
            relevant_experience=experience_context(current_challenge, state),
        )

    planner = JsonPlanner(
        requester,
        tool_schemas=registry.schemas(),
        intelligence_context_provider=intelligence_context,
        domain_context_provider=domain_context,
        domain_runtime_context_provider=domain_runtime_context,
        experiment_context_provider=experiment_context,
        experience_context_provider=experience_context,
        web_attack_surface_context_provider=web_attack_surface_context,
        web_research_context_provider=web_research_context,
    )
    analysis_delegate = JsonAnalyzer(requester)
    if selected_runtime_domain == "web":
        analysis_delegate = WebIntelligenceAnalyzer(analysis_delegate)
    analyzer = DomainRuntimeAnalyzer(analysis_delegate, domain_runtime_manager)
    tool_runtime = ToolRuntime(
        registry=registry,
        policy_engine=PolicyEngine(),
        approval_manager=ApprovalManager(),
        approval_resolver=approval_resolver,
    )
    executor = ToolRuntimeExecutor(
        tool_runtime=tool_runtime,
        workspace_manager=WorkspaceManager(execution.workspace_root),
        execution_mode=execution.mode,
    )
    effective_flag_confirmer = flag_confirmer
    if web_research_manager is not None and flag_confirmer is not None:
        def confirm_web_flag(candidate: object) -> bool:
            accepted = bool(flag_confirmer(candidate))
            web_research_manager.verify_flag(candidate, accepted)
            return accepted

        effective_flag_confirmer = confirm_web_flag
    runtime = AgentRuntime(
        challenge=challenge,
        planner=planner,
        executor=executor,
        analyzer=analyzer,
        budget=budget,
        tool_schemas=registry.schemas(),
        flag_confirmer=effective_flag_confirmer,
        intelligence_store=intelligence_store,
        initial_state=resume_checkpoint.run_state if resume_checkpoint is not None else None,
        initial_step_checkpoint=(
            resume_checkpoint.step_checkpoint
            if resume_checkpoint is not None
            else None
        ),
    )
    runtime.domain_selection = domain_selection
    runtime.domain_runtime_manager = domain_runtime_manager
    runtime.domain_runtime_state = domain_runtime_state
    experiment_runtime_state = (
        resume_checkpoint.experiment_runtime_state
        if resume_checkpoint is not None
        and resume_checkpoint.experiment_runtime_state is not None
        else ExperimentRuntimeState(
            run_id=runtime.state.run_id,
            challenge_id=challenge.challenge_id,
        )
    )
    autonomous_experiment_loop = AutonomousExperimentLoop(
        intelligence_store,
        experiment_runtime_state,
        domain_manager=domain_runtime_manager,
        experience_context_provider=lambda: experience_context(
            challenge,
            runtime.state,
        ),
    )
    experiment_orchestrator = ExperimentOrchestrator(
        intelligence_store,
        experiment_runtime_state,
        autonomous_loop=autonomous_experiment_loop,
    )
    runtime.experiment_orchestrator = experiment_orchestrator
    runtime.experiment_manager = experiment_orchestrator.experiment_manager
    runtime.experiment_runtime_manager = experiment_orchestrator.runtime_manager
    runtime.autonomous_experiment_loop = autonomous_experiment_loop
    runtime.experience_store = experience_store
    runtime.experience_retriever = experience_retriever
    runtime.web_session_manager = web_session_manager
    runtime.web_research_manager = web_research_manager
    runtime.mcp_server_registry = mcp_server_registry
    runtime.mcp_client_manager = mcp_client_manager
    checkpoint_root = config.get("checkpoint_dir", "./checkpoints")
    if not isinstance(checkpoint_root, str) or not checkpoint_root.strip():
        checkpoint_root = "./checkpoints"
    checkpoint_path = (
        resume_checkpoint.checkpoint_directory
        if resume_checkpoint is not None
        and resume_checkpoint.checkpoint_directory is not None
        else Path(checkpoint_root) / f"r4_{runtime.state.run_id}"
    )
    runtime.checkpoint_handler = RuntimeStepCheckpoint(
        IntelligenceCheckpoint(checkpoint_path),
        intelligence_store,
        artifacts_provider=executor.artifacts_for_current_workspace,
        domain_state_provider=lambda: domain_runtime_manager.current()[1],
        experiment_runtime_provider=lambda: experiment_orchestrator.state,
    )
    tool_runtime.event_callback = runtime.record_tool_event
    return runtime
