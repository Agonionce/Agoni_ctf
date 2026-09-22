"""R11 deterministic fake-local Web autonomous research demonstration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.challenge.importer import ChallengeImporter
from agent.completion.collector import CompletionCollector
from agent.domains.integration import DomainRuntimeAnalyzer
from agent.domains.manager import build_default_runtime_manager
from agent.domains.web.research.manager import WebResearchManager
from agent.domains.web.research.models import WebFlagVerificationStatus
from agent.domains.web.research.session import WebSessionManager
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.checkpoint import IntelligenceCheckpoint, RuntimeStepCheckpoint
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluationStatus,
    ExperimentRuntimeState,
)
from agent.intelligence.experiment.runtime.loop import AutonomousExperimentLoop
from agent.intelligence.experiment.runtime.orchestrator import ExperimentOrchestrator
from agent.intelligence.models import ArtifactReference, KnowledgeUpdateSuggestion
from agent.intelligence.store import IntelligenceStore
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    DecisionType,
    FlagCandidate,
    RunBudget,
    RunState,
    ToolCall,
)
from agent.runtime.runtime import AgentRuntime
from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
    ToolRiskLevel,
)
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime, ToolRuntimeExecutor
from agent.workspace.manager import WorkspaceManager


DEMO_TOKEN = "LOCAL_WEB_AUTONOMOUS_RESEARCH_OK"


class FakeLocalWebTool(Tool):
    metadata = ToolMetadata(
        name="fake_local_web",
        description="Capture deterministic fake-local Web observations for R11.",
        risk_level=ToolRiskLevel.LOW,
        requires_network=False,
        writes_files=True,
        execution_type="fake_local_web",
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["model", "compare"]}},
        "required": ["mode"],
        "additionalProperties": False,
    }

    def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        mode = str(arguments["mode"])
        observation = (
            "endpoint and parameter identified"
            if mode == "model"
            else f"response behavior changed {DEMO_TOKEN}"
        )
        artifact = context.output_dir / f"r11-{mode}.json"
        artifact.write_text(
            json.dumps({
                "source": "authorized fake local Web challenge",
                "mode": mode,
                "observation": observation,
            }, indent=2),
            encoding="utf-8",
        )
        evidence = [{
            "evidence_type": "ENDPOINT_DISCOVERED",
            "observation": "Endpoint /article returned status 200",
            "request_id": f"fake-{mode}",
            "endpoint": "/article",
        }]
        if mode == "model":
            evidence.append({
                "evidence_type": "PARAMETER_IDENTIFIED",
                "observation": "Parameter id was observed at /article",
                "request_id": "fake-model",
                "endpoint": "/article",
                "parameter": "id",
            })
        else:
            evidence.append({
                "evidence_type": "RESPONSE_BEHAVIOR",
                "observation": "response behavior changed",
                "request_id": "fake-compare",
                "endpoint": "/article",
                "parameter": "id",
            })
        return ToolExecutionOutput(
            True,
            stdout=observation,
            artifact_paths=[artifact],
            artifact_type="fake_web_response",
            metadata={
                "web_observation": {
                    "request_id": f"fake-{mode}",
                    "method": "GET",
                    "base_url": "http://127.0.0.1:8000",
                    "endpoint": "/article",
                    "parameters": ["id"],
                    "status_code": 200,
                    "technologies": ["FakeWeb/1.0"],
                    "cookies": {},
                },
                "web_evidence": evidence,
            },
        )


class R11Planner:
    def __init__(self, experiment_state: ExperimentRuntimeState) -> None:
        self.experiment_state = experiment_state

    def plan(self, challenge, state, tool_schemas):
        del challenge, tool_schemas
        if state.current_step == 0:
            return ActionProposal(
                "build the fake-local Web application model",
                "capture a provenance-bearing endpoint observation",
                [ToolCall("model", "fake_local_web", {"mode": "model"})],
            )
        selected = self.experiment_state.active_candidates[0]
        return ActionProposal(
            "test the ranked Web response hypothesis",
            "execute one evidence-bound fake-local comparison through ToolRuntime",
            [ToolCall("compare", "fake_local_web", {"mode": "compare"})],
            metadata={"experiment": {
                "hypothesis_id": selected.hypothesis_id,
                "hypothesis_statement": "",
                "hypothesis_domain": "web",
                "hypothesis_confidence": selected.confidence,
                "goal": selected.suggested_goal,
                "expected_result": "response behavior changed",
                "experiment_type": selected.experiment_type or "PARAMETER_BEHAVIOR",
                "evidence_type": selected.evidence_type or "RESPONSE_BEHAVIOR",
                "experience_influence": list(selected.experience_influence),
            }},
            decision_type=DecisionType.EXPERIMENT_ACTION,
        )


class R11Analyzer:
    def analyze(self, observation, state):
        del state
        if observation.step_id == 1:
            artifact_id = observation.tool_results[0].artifact_refs[0]
            return AnalysisResult(
                "the fake Web application exposes /article with parameter id",
                AnalysisOutcome.PROGRESS,
                confidence=0.8,
                knowledge_updates=[KnowledgeUpdateSuggestion(
                    "hypothesis",
                    {
                        "statement": "Parameter id at /article affects response behavior.",
                        "domain": "web",
                        "confidence": 0.6,
                        "priority": "HIGH",
                        "experiment_goal": "compare authorized local responses for parameter id",
                        "expected_result": "response behavior changed",
                        "experiment_type": "PARAMETER_BEHAVIOR",
                        "evidence_type": "RESPONSE_BEHAVIOR",
                    },
                    artifact_refs=[ArtifactReference(artifact_id, "hypothesis_source")],
                )],
            )
        return AnalysisResult(
            "the fake-local response comparison produced structured evidence",
            AnalysisOutcome.PROGRESS,
            flag_candidates=[FlagCandidate(
                DEMO_TOKEN,
                "fake local challenge controller",
                1.0,
                "the evidence-bound comparison reached the local completion marker",
            )],
            confidence=1.0,
        )


def run_demo(root: str | Path) -> str:
    root = Path(root)
    imported = ChallengeImporter(
        workspace_root=root / "workspace",
        experience_root=root / "experiences" / "challenges",
        source_root=root,
    ).import_challenge(
        name="R11 Fake Local Web",
        domain="web",
        description="Understand and compare one authorized fake-local Web endpoint.",
        target_url="http://127.0.0.1:8000",
        authorization_scope="authorized_local_demo",
        entropy="r11-demo",
    )
    challenge = imported.manifest.to_challenge_spec()
    run_state = RunState(challenge, run_id="r11-fake-local-run")
    store = IntelligenceStore.create(challenge.challenge_id)
    experiment_state = ExperimentRuntimeState(run_state.run_id, challenge.challenge_id)
    domain_manager = build_default_runtime_manager()
    domain_state = domain_manager.initialize("web", challenge)
    assert isinstance(domain_state, WebRuntimeState)
    WebSessionManager(domain_state.sessions).create(
        "http://127.0.0.1:8000",
        session_id="default",
    )
    loop = AutonomousExperimentLoop(
        store,
        experiment_state,
        domain_manager=domain_manager,
        experience_context_provider=lambda: {"relevant_experience": [{
            "id": "experience-web-baseline",
            "domain": "web",
            "category": "response_comparison",
            "trigger": "parameter behavior",
            "pattern": "compare against a stable endpoint baseline",
            "strategy": "compare authorized local responses for parameter id",
            "lesson": "preserve both response observations",
            "confidence": 0.8,
        }]},
    )
    orchestrator = ExperimentOrchestrator(store, experiment_state, autonomous_loop=loop)
    registry = ToolRegistry()
    registry.register(FakeLocalWebTool())
    tool_runtime = ToolRuntime(registry, PolicyEngine(), ApprovalManager())
    executor = ToolRuntimeExecutor(
        tool_runtime,
        WorkspaceManager(root / "workspace"),
        execution_mode="autonomous_local",
    )
    web_research = WebResearchManager(domain_state)

    def confirm(candidate: object) -> bool:
        accepted = getattr(candidate, "value", "") == DEMO_TOKEN
        web_research.verify_flag(candidate, accepted)
        return accepted

    checkpoint = IntelligenceCheckpoint(root / "checkpoint")
    runtime = AgentRuntime(
        challenge,
        R11Planner(experiment_state),
        executor,
        DomainRuntimeAnalyzer(R11Analyzer(), domain_manager),
        budget=RunBudget(max_steps=3, max_llm_calls=8),
        tool_schemas=registry.schemas(),
        intelligence_store=store,
        initial_state=run_state,
        experiment_orchestrator=orchestrator,
        flag_confirmer=confirm,
    )
    runtime.checkpoint_handler = RuntimeStepCheckpoint(
        checkpoint,
        store,
        artifacts_provider=executor.artifacts_for_current_workspace,
        domain_state_provider=lambda: domain_state,
        experiment_runtime_provider=lambda: experiment_state,
    )
    tool_runtime.event_callback = runtime.record_tool_event

    result = runtime.run()
    record = experiment_state.records[0]
    if record.evaluation is None or record.evaluation.status is not ExperimentEvaluationStatus.SUPPORTED:
        raise RuntimeError("R11 structured Web evidence was not evaluated as SUPPORTED")
    if not domain_state.application_model.parameters:
        raise RuntimeError("R11 Web application model did not record the parameter")
    if not domain_state.web_experiments or not domain_state.web_evidence:
        raise RuntimeError("R11 Web experiment or evidence projection is missing")
    if domain_state.flag_candidates[0].verification_status is not WebFlagVerificationStatus.VERIFIED:
        raise RuntimeError("R11 flag candidate did not pass explicit verification")
    if not any(
        "experience-web-baseline" in item.experience_influence
        for item in experiment_state.active_candidates
    ):
        raise RuntimeError("R11 retrieved experience did not influence research")
    restored = checkpoint.load().domain_runtime_state
    if not isinstance(restored, WebRuntimeState) or not restored.web_evidence:
        raise RuntimeError("R11 Web research state did not restore from checkpoint")
    if restored.flag_candidates[0].verification_status is not WebFlagVerificationStatus.VERIFIED:
        raise RuntimeError("R11 verified candidate state did not restore")
    report = CompletionCollector().collect(
        imported.manifest,
        result,
        store.state,
        executor.artifacts_for_current_workspace(),
    )
    if (
        report.flag_verification.get("status") != "VERIFIED"
        or report.flag_verification.get("candidate_value") != DEMO_TOKEN
    ):
        raise RuntimeError("R11 completion flag verification is not visible in the local report")
    return DEMO_TOKEN


def main() -> None:
    with TemporaryDirectory(prefix="agonionce-r11-") as directory:
        print(run_demo(Path(directory)))


if __name__ == "__main__":
    main()
