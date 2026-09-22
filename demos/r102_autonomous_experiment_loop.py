"""R10.2 deterministic fake-local autonomous experiment loop demonstration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.domains.integration import DomainRuntimeAnalyzer
from agent.domains.manager import build_default_runtime_manager
from agent.intelligence.checkpoint import IntelligenceCheckpoint, RuntimeStepCheckpoint
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluationStatus,
    ExperimentRuntimeState,
)
from agent.intelligence.experiment.runtime.loop import AutonomousExperimentLoop
from agent.intelligence.experiment.runtime.orchestrator import ExperimentOrchestrator
from agent.intelligence.models import (
    ArtifactReference,
    HypothesisStatus,
    KnowledgeUpdateSuggestion,
)
from agent.intelligence.store import IntelligenceStore
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
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


DEMO_TOKEN = "LOCAL_AUTONOMOUS_EXPERIMENT_LOOP_OK"


class FakeLocalResearchTool(Tool):
    metadata = ToolMetadata(
        name="fake_local_research",
        description="Create deterministic local observations for an R10.2 demo.",
        risk_level=ToolRiskLevel.LOW,
        requires_network=False,
        writes_files=True,
        execution_type="fake_local_demo",
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["observe", "compare"]}
        },
        "required": ["mode"],
        "additionalProperties": False,
    }

    def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        mode = str(arguments["mode"])
        payload = {
            "source": "authorized fake local challenge",
            "mode": mode,
            "observation": (
                "parameter id observed"
                if mode == "observe"
                else f"response changed {DEMO_TOKEN}"
            ),
        }
        artifact = context.output_dir / f"r102-{mode}.json"
        artifact.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return ToolExecutionOutput(
            True,
            stdout=str(payload["observation"]),
            artifact_paths=[artifact],
            artifact_type="experiment_fixture",
            metadata={
                "web_observation": {
                    "base_url": "http://localhost/fake",
                    "endpoint": "/item",
                    "parameters": ["id"],
                    "technologies": ["fake-local"],
                }
            },
        )


class TwoStepResearchPlanner:
    def __init__(self, experiment_state: ExperimentRuntimeState) -> None:
        self.experiment_state = experiment_state

    def plan(self, challenge, state, tool_schemas):
        del challenge, tool_schemas
        if state.current_step == 0:
            return ActionProposal(
                "observe the fake local challenge",
                "collect the first provenance-bearing local artifact",
                [ToolCall("observe-call", "fake_local_research", {"mode": "observe"})],
            )
        selected = self.experiment_state.active_candidates[0]
        return ActionProposal(
            "verify the highest-value hypothesis",
            "use the R10.2 ranked research recommendation through ToolRuntime",
            [ToolCall("compare-call", "fake_local_research", {"mode": "compare"})],
            metadata={
                "experiment": {
                    "hypothesis_id": selected.hypothesis_id,
                    "hypothesis_statement": "",
                    "hypothesis_domain": selected.domain,
                    "hypothesis_confidence": selected.confidence,
                    "goal": selected.suggested_goal,
                    "expected_result": "response changed",
                }
            },
            decision_type=DecisionType.EXPERIMENT_ACTION,
        )


class FakeResearchAnalyzer:
    def analyze(self, observation, state):
        del state
        if observation.step_id == 1:
            artifact_id = observation.tool_results[0].artifact_refs[0]
            return AnalysisResult(
                "the local endpoint exposes an id parameter",
                AnalysisOutcome.PROGRESS,
                recommendations="rank a bounded response-comparison experiment",
                confidence=0.8,
                knowledge_updates=[
                    KnowledgeUpdateSuggestion(
                        "hypothesis",
                        {
                            "statement": "Parameter id at /item affects response behavior.",
                            "domain": "web",
                            "confidence": 0.6,
                            "priority": "HIGH",
                            "experiment_goal": "compare bounded local responses for parameter id",
                            "expected_result": "response changed",
                        },
                        artifact_refs=[
                            ArtifactReference(artifact_id, "hypothesis_source")
                        ],
                    )
                ],
            )
        return AnalysisResult(
            "the comparison produced provenance-bearing evidence",
            AnalysisOutcome.PROGRESS,
            flag_candidates=[
                FlagCandidate(
                    DEMO_TOKEN,
                    "fake local demo controller",
                    1.0,
                    observation.tool_results[0].stdout,
                )
            ],
            confidence=1.0,
        )


def run_demo(root: str | Path) -> str:
    root = Path(root)
    challenge = ChallengeSpec(
        "r102-fake-local",
        "R10.2 fake local research loop",
        "Observe and compare a deterministic local parameter.",
        category="web",
        authorization_scope="authorized_local_demo",
        metadata={"entry_points": ["/item"]},
    )
    run_state = RunState(challenge, run_id="r102-fake-local-run")
    store = IntelligenceStore.create(challenge.challenge_id)
    experiment_state = ExperimentRuntimeState(
        run_state.run_id,
        challenge.challenge_id,
    )
    domain_manager = build_default_runtime_manager()
    domain_state = domain_manager.initialize("web", challenge)
    loop = AutonomousExperimentLoop(
        store,
        experiment_state,
        domain_manager=domain_manager,
        experience_context_provider=lambda: {
            "relevant_experience": [
                {
                    "id": "experience-local-pattern",
                    "domain": "web",
                    "category": "behavior_comparison",
                    "trigger": "parameter response behavior",
                    "pattern": "compare a stable baseline before drawing a conclusion",
                    "strategy": "compare bounded local responses for parameter id",
                    "lesson": "preserve both response artifacts",
                    "confidence": 0.8,
                }
            ]
        },
    )
    orchestrator = ExperimentOrchestrator(
        store,
        experiment_state,
        autonomous_loop=loop,
    )
    registry = ToolRegistry()
    registry.register(FakeLocalResearchTool())
    tool_runtime = ToolRuntime(registry, PolicyEngine(), ApprovalManager())
    executor = ToolRuntimeExecutor(
        tool_runtime,
        WorkspaceManager(root / "workspace"),
        execution_mode="autonomous_local",
    )
    checkpoint = IntelligenceCheckpoint(root / "checkpoint")
    runtime = AgentRuntime(
        challenge,
        TwoStepResearchPlanner(experiment_state),
        executor,
        DomainRuntimeAnalyzer(FakeResearchAnalyzer(), domain_manager),
        budget=RunBudget(max_steps=3, max_llm_calls=8),
        tool_schemas=registry.schemas(),
        intelligence_store=store,
        initial_state=run_state,
        experiment_orchestrator=orchestrator,
        flag_confirmer=lambda candidate: candidate.value == DEMO_TOKEN,
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

    if len(result.steps) != 2 or len(experiment_state.records) != 1:
        raise RuntimeError("the fake autonomous loop did not complete two decisions")
    record = experiment_state.records[0]
    if record.evaluation is None or (
        record.evaluation.status is not ExperimentEvaluationStatus.SUPPORTED
    ):
        raise RuntimeError("the fake experiment was not evaluated as SUPPORTED")
    hypothesis = store.get_hypothesis(record.hypothesis_id)
    if hypothesis is None or hypothesis.status is not HypothesisStatus.SUPPORTED:
        raise RuntimeError("evaluation feedback did not update the hypothesis")
    if not record.feedback_applied or not experiment_state.decision_history:
        raise RuntimeError("feedback or decision history was not persisted")
    if "experience-local-pattern" not in hypothesis.experience_influence:
        raise RuntimeError("retrieved experience did not influence the research decision")
    restored = checkpoint.load()
    if restored.experiment_runtime_state is None or (
        restored.experiment_runtime_state.loop_iteration != 2
    ):
        raise RuntimeError("the autonomous loop did not restore consistently")
    return DEMO_TOKEN


def main() -> None:
    with TemporaryDirectory(prefix="agonionce-r102-") as directory:
        print(run_demo(Path(directory)))


if __name__ == "__main__":
    main()
