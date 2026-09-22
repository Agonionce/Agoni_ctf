"""R10.1 fake-local Experiment Runtime Integration demonstration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.intelligence.checkpoint import IntelligenceCheckpoint, RuntimeStepCheckpoint
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluationStatus,
    ExperimentRuntimeState,
    ExperimentRuntimeStatus,
)
from agent.intelligence.experiment.runtime.orchestrator import ExperimentOrchestrator
from agent.intelligence.models import HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.policy.approval import ApprovalManager
from agent.policy.engine import PolicyEngine
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    DecisionType,
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


DEMO_TOKEN = "LOCAL_EXPERIMENT_RUNTIME_OK"


class FakeEvidenceTool(Tool):
    metadata = ToolMetadata(
        name="fake_evidence_tool",
        description="Produce one deterministic fake-local response artifact.",
        risk_level=ToolRiskLevel.MEDIUM,
        requires_network=False,
        writes_files=True,
        execution_type="fake_local_demo",
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {"case": {"type": "string", "enum": ["changed"]}},
        "required": ["case"],
        "additionalProperties": False,
    }

    def execute(
        self,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        if arguments.get("case") != "changed":
            return ToolExecutionOutput(False, error="unknown fake-local case")
        artifact = context.output_dir / "fake-experiment-response.json"
        artifact.write_text(
            json.dumps(
                {
                    "source": "authorized fake local challenge",
                    "observation": "response changed",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return ToolExecutionOutput(
            True,
            stdout="response changed",
            artifact_paths=[artifact],
            artifact_type="experiment_fixture",
        )


class FakeExperimentPlanner:
    def plan(self, challenge, state, tool_schemas):
        del challenge, state, tool_schemas
        return ActionProposal(
            objective="verify fake endpoint behavior",
            reasoning_summary="test one local hypothesis with traceable evidence",
            actions=[
                ToolCall(
                    "fake-experiment-call",
                    "fake_evidence_tool",
                    {"case": "changed"},
                )
            ],
            metadata={
                "experiment": {
                    "hypothesis_id": "",
                    "hypothesis_statement": "id parameter affects the fake response",
                    "hypothesis_domain": "web",
                    "hypothesis_confidence": 0.5,
                    "goal": "verify endpoint behavior",
                    "expected_result": "response changed",
                }
            },
            decision_type=DecisionType.EXPERIMENT_ACTION,
        )


class FakeEvidenceAnalyzer:
    def analyze(self, observation, state):
        del state
        return AnalysisResult(
            summary="experiment evidence is ready for human review",
            outcome=AnalysisOutcome.PROGRESS,
            recommendations="review the deterministic evaluation before the next decision",
            confidence=0.8 if observation.tool_results[0].success else 0.0,
        )


def run_demo(root: str | Path) -> str:
    root = Path(root)
    challenge = ChallengeSpec(
        "r101-fake-local",
        "R10.1 fake local experiment",
        "A deterministic fake response changes after one controlled action.",
        category="web",
        authorization_scope="authorized_local_demo",
    )
    run_state = RunState(challenge, run_id="r101-fake-local-run")
    intelligence_store = IntelligenceStore.create(challenge.challenge_id)
    experiment_state = ExperimentRuntimeState(
        run_state.run_id,
        challenge.challenge_id,
    )
    orchestrator = ExperimentOrchestrator(
        intelligence_store,
        experiment_state,
    )
    registry = ToolRegistry()
    registry.register(FakeEvidenceTool())
    workspace_manager = WorkspaceManager(root / "workspace")
    tool_runtime = ToolRuntime(
        registry,
        PolicyEngine(),
        ApprovalManager(),
    )
    executor = ToolRuntimeExecutor(
        tool_runtime,
        workspace_manager,
        execution_mode="autonomous_local",
    )
    checkpoint = IntelligenceCheckpoint(root / "checkpoint")
    runtime = AgentRuntime(
        challenge,
        FakeExperimentPlanner(),
        executor,
        FakeEvidenceAnalyzer(),
        budget=RunBudget(max_steps=1, max_llm_calls=4),
        tool_schemas=registry.schemas(),
        intelligence_store=intelligence_store,
        initial_state=run_state,
        experiment_orchestrator=orchestrator,
    )
    runtime.checkpoint_handler = RuntimeStepCheckpoint(
        checkpoint,
        intelligence_store,
        artifacts_provider=executor.artifacts_for_current_workspace,
        experiment_runtime_provider=lambda: experiment_state,
    )
    tool_runtime.event_callback = runtime.record_tool_event

    result = runtime.run()

    if len(result.steps) != 1:
        raise RuntimeError("fake experiment did not complete one Runtime step")
    record = experiment_state.records[0]
    if record.status is not ExperimentRuntimeStatus.COMPLETED:
        raise RuntimeError("experiment runtime did not complete")
    if record.evaluation is None or (
        record.evaluation.status is not ExperimentEvaluationStatus.SUPPORTED
    ):
        raise RuntimeError("experiment evaluator did not return SUPPORTED")
    if len(record.evidence_ids) != 1:
        raise RuntimeError("experiment evidence was not persisted")
    evidence = intelligence_store.get_evidence(record.evidence_ids[0])
    if evidence is None or not evidence.observation_id or not evidence.artifact_refs:
        raise RuntimeError("experiment evidence provenance is incomplete")
    hypothesis = intelligence_store.get_hypothesis(record.hypothesis_id)
    if hypothesis is None or hypothesis.status is not HypothesisStatus.OPEN:
        raise RuntimeError("evaluation bypassed human hypothesis review")
    tool_result = result.steps[0].tool_results[0]
    if tool_result.policy_decision is None or (
        tool_result.policy_decision.get("decision") != "ALLOW"
    ):
        raise RuntimeError("experiment Tool did not pass through PolicyEngine")
    restored = checkpoint.load()
    if restored.experiment_runtime_state is None:
        raise RuntimeError("experiment_runtime.json was not restored")
    return DEMO_TOKEN


def main() -> None:
    with TemporaryDirectory(prefix="agonionce-r101-") as directory:
        print(run_demo(Path(directory)))


if __name__ == "__main__":
    main()
