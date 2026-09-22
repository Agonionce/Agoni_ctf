from __future__ import annotations

from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from agent.intelligence.checkpoint import IntelligenceCheckpoint, RuntimeStepCheckpoint
from agent.intelligence.experiment.context import ExperimentContextBuilder
from agent.intelligence.experiment.models import EvidenceRecord, Experiment, ExperimentStatus
from agent.intelligence.experiment.runtime.evaluator import (
    EvidenceFactory,
    EvidenceProvenanceError,
    ExperimentEvaluator,
)
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluation,
    ExperimentEvaluationStatus,
    ExperimentRuntimeManager,
    ExperimentRuntimeState,
    ExperimentRuntimeStatus,
)
from agent.intelligence.experiment.runtime.orchestrator import ExperimentOrchestrator
from agent.intelligence.models import ArtifactReference
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    DecisionType,
    FlagCandidate,
    RunBudget,
    RunState,
    RunStatus,
    ToolCall,
    ToolResult,
)
from agent.runtime.planner import JsonPlanner
from agent.runtime.runtime import AgentRuntime
from cli.app import app


runner = CliRunner()


def _proposal(*, hypothesis_id: str = "") -> ActionProposal:
    return ActionProposal(
        objective="verify fake endpoint behavior",
        reasoning_summary="run one bounded, local experiment",
        actions=[
            ToolCall(
                "experiment-call",
                "fake_evidence_tool",
                {"case": "changed"},
            )
        ],
        metadata={
            "experiment": {
                "hypothesis_id": hypothesis_id,
                "hypothesis_statement": (
                    "id parameter affects the fake response"
                    if not hypothesis_id
                    else ""
                ),
                "hypothesis_domain": "web",
                "hypothesis_confidence": 0.5,
                "goal": "verify endpoint behavior",
                "expected_result": "response changed",
            }
        },
        decision_type=DecisionType.EXPERIMENT_ACTION,
    )


def _runtime_state(challenge: ChallengeSpec, run_id: str = "run-r101"):
    store = IntelligenceStore.create(challenge.challenge_id)
    state = ExperimentRuntimeState(run_id, challenge.challenge_id)
    return store, state, ExperimentOrchestrator(store, state)


def test_experiment_runtime_lifecycle_created_running_completed_and_failed():
    state = ExperimentRuntimeState("run-lifecycle", "challenge-lifecycle")
    manager = ExperimentRuntimeManager(state)
    completed = manager.create(
        step_id=1,
        call_id="call-1",
        hypothesis_id="hypothesis-1",
        experiment_id="experiment-1",
        proposal_fingerprint="a" * 64,
        proposal={"objective": "test"},
    )
    assert completed.status is ExperimentRuntimeStatus.CREATED
    manager.start(completed.experiment_id)
    assert completed.status is ExperimentRuntimeStatus.RUNNING
    evaluation = ExperimentEvaluation(
        completed.experiment_id,
        ExperimentEvaluationStatus.INCONCLUSIVE,
        "No conclusive signal was observed.",
        (),
    )
    manager.finish(
        completed.experiment_id,
        successful=True,
        observation_id="observation-1",
        evidence_ids=(),
        evaluation=evaluation,
        tool_results=({"call_id": "call-1"},),
    )
    assert completed.status is ExperimentRuntimeStatus.COMPLETED

    failed = manager.create(
        step_id=2,
        call_id="call-2",
        hypothesis_id="hypothesis-2",
        experiment_id="experiment-2",
        proposal_fingerprint="b" * 64,
        proposal={"objective": "test failure"},
    )
    manager.start(failed.experiment_id)
    failed_evaluation = ExperimentEvaluation(
        failed.experiment_id,
        ExperimentEvaluationStatus.INCONCLUSIVE,
        "Controlled execution failed.",
        (),
    )
    manager.finish(
        failed.experiment_id,
        successful=False,
        observation_id="observation-2",
        evidence_ids=(),
        evaluation=failed_evaluation,
        tool_results=({"call_id": "call-2"},),
    )
    assert failed.status is ExperimentRuntimeStatus.FAILED


def test_planner_extension_accepts_experiment_and_preserves_legacy_output():
    legacy = JsonPlanner._proposal_from_payload(
        {
            "objective": "read a fixture",
            "reasoning_summary": "legacy planner output",
            "actions": [{"tool_name": "fake", "arguments": {}}],
        }
    )
    experiment = JsonPlanner._proposal_from_payload(
        {
            "decision_type": "experiment",
            "objective": "test a response",
            "reasoning_summary": "one controlled comparison",
            "hypothesis_statement": "id parameter affects response",
            "hypothesis_domain": "web",
            "experiment_goal": "verify endpoint behavior",
            "expected_result": "response changed",
            "action": {
                "call_id": "experiment-call",
                "tool_name": "fake",
                "arguments": {"id": "2"},
            },
        }
    )

    assert legacy.decision_type is DecisionType.NORMAL_ACTION
    assert experiment.decision_type is DecisionType.EXPERIMENT_ACTION
    assert experiment.actions[0].tool_name == "fake"
    assert experiment.metadata["experiment"]["goal"] == "verify endpoint behavior"


def test_orchestrator_binds_existing_or_new_hypothesis_without_execution():
    challenge = ChallengeSpec("r101-binding", "Binding", "authorized local fixture")
    store, state, orchestrator = _runtime_state(challenge)
    existing = orchestrator.experiment_manager.create_hypothesis(
        "existing hypothesis",
        "web",
        0.4,
    )

    record = orchestrator.prepare(
        _proposal(hypothesis_id=existing.id),
        step_id=1,
        run_id=state.run_id,
        challenge_id=challenge.challenge_id,
    )

    assert record is not None
    assert record.hypothesis_id == existing.id
    assert record.status is ExperimentRuntimeStatus.RUNNING
    experiment = store.get_experiment(record.experiment_id)
    assert experiment is not None
    assert experiment.hypothesis_id == existing.id
    assert experiment.status is ExperimentStatus.RUNNING

    second = orchestrator.prepare(
        _proposal(),
        step_id=2,
        run_id=state.run_id,
        challenge_id=challenge.challenge_id,
    )
    assert second is not None
    assert second.hypothesis_id != existing.id
    assert store.get_hypothesis(second.hypothesis_id) is not None


def test_evidence_factory_requires_artifact_and_binds_all_provenance():
    factory = EvidenceFactory()
    result = ToolResult(
        "call-1",
        "fake",
        True,
        stdout="response changed",
        artifact_refs=["artifact-001"],
    )

    evidence = factory.create(
        result,
        experiment_id="experiment-1",
        hypothesis_id="hypothesis-1",
        observation_id="observation-1",
    )

    assert evidence.experiment_id == "experiment-1"
    assert evidence.hypothesis_id == "hypothesis-1"
    assert evidence.observation_id == "observation-1"
    assert evidence.artifact_refs == [
        ArtifactReference("artifact-001", "experiment_evidence")
    ]
    assert evidence.source == "ToolResult:fake:call-1"
    with pytest.raises(EvidenceProvenanceError, match="artifact"):
        factory.create(
            ToolResult("call-2", "fake", True, stdout="unbound"),
            experiment_id="experiment-1",
            hypothesis_id="hypothesis-1",
            observation_id="observation-2",
        )


@pytest.mark.parametrize(
    ("observation", "expected_status"),
    [
        ("response changed", ExperimentEvaluationStatus.SUPPORTED),
        ("response unchanged and identical", ExperimentEvaluationStatus.CONTRADICTED),
        ("status code was recorded", ExperimentEvaluationStatus.INCONCLUSIVE),
    ],
)
def test_experiment_evaluator_is_deterministic(observation, expected_status):
    experiment = Experiment(
        hypothesis_id="hypothesis-1",
        goal="compare response",
        action={"tool_name": "fake", "arguments": {}},
        expected_result="response changed",
        experiment_id="experiment-1",
    )
    evidence = EvidenceRecord(
        source="ToolResult:fake:call-1",
        observation=observation,
        artifact_refs=[ArtifactReference("artifact-001", "experiment_evidence")],
        experiment_id=experiment.experiment_id,
        hypothesis_id=experiment.hypothesis_id,
        observation_id="observation-1",
    )
    result = ToolResult(
        "call-1",
        "fake",
        True,
        stdout=observation,
        artifact_refs=["artifact-001"],
    )

    evaluation = ExperimentEvaluator().evaluate(experiment, [evidence], [result])

    assert evaluation.status is expected_status
    assert evaluation.evidence_refs == (evidence.evidence_id,)


def test_experiment_evaluator_rejects_expected_change_when_response_repeats():
    experiment = Experiment(
        hypothesis_id="hypothesis-repeat",
        goal="compare fake response",
        action={"tool_name": "fake", "arguments": {}},
        expected_result="response changed",
        experiment_id="experiment-repeat",
    )
    evidence = EvidenceRecord(
        source="ToolResult:fake:repeat",
        observation="response_repeat=true; previous_observations=1",
        artifact_refs=[ArtifactReference("artifact-repeat", "experiment_evidence")],
        experiment_id=experiment.experiment_id,
        hypothesis_id=experiment.hypothesis_id,
        observation_id="observation-repeat",
    )
    result = ToolResult(
        "repeat",
        "fake",
        True,
        stdout="unchanged response",
        artifact_refs=["artifact-repeat"],
    )

    evaluation = ExperimentEvaluator().evaluate(experiment, [evidence], [result])

    assert evaluation.status is ExperimentEvaluationStatus.CONTRADICTED


class _OneExperimentPlanner:
    def plan(self, challenge, state, tool_schemas):
        del challenge, state, tool_schemas
        return _proposal()


class _CountingEvidenceExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, proposal):
        self.calls += 1
        return [
            ToolResult(
                proposal.actions[0].call_id,
                proposal.actions[0].tool_name,
                True,
                stdout="response changed LOCAL_R101_RECOVERY_OK",
                artifact_refs=["artifact-001"],
            )
        ]


class _SupportedAnalyzer:
    def analyze(self, observation, state):
        del state
        return AnalysisResult(
            "experiment evidence is available for human review",
            AnalysisOutcome.PROGRESS,
            flag_candidates=[
                FlagCandidate(
                    "LOCAL_R101_RECOVERY_OK",
                    "fake test fixture",
                    1.0,
                    observation.tool_results[0].stdout,
                )
            ],
            confidence=1.0,
        )


class _InterruptAfterExperimentResult:
    def __init__(self, delegate):
        self.delegate = delegate

    def record(self, stage, *args, **kwargs):
        result = self.delegate.record(stage, *args, **kwargs)
        if stage == "experiment_result":
            raise RuntimeError("simulated crash after durable experiment result")
        return result


def test_checkpoint_recovery_does_not_repeat_completed_experiment(tmp_path):
    challenge = ChallengeSpec(
        "r101-recovery",
        "Recovery",
        "authorized local checkpoint fixture",
    )
    run_state = RunState(challenge, run_id="run-r101-recovery")
    store = IntelligenceStore.create(challenge.challenge_id)
    experiment_state = ExperimentRuntimeState(
        run_state.run_id,
        challenge.challenge_id,
    )
    orchestrator = ExperimentOrchestrator(store, experiment_state)
    checkpoint = IntelligenceCheckpoint(tmp_path / "checkpoint")
    writer = RuntimeStepCheckpoint(
        checkpoint,
        store,
        artifacts_provider=lambda: [
            {"artifact_id": "artifact-001", "path": "output/fake.json"}
        ],
        experiment_runtime_provider=lambda: experiment_state,
    )
    executor = _CountingEvidenceExecutor()
    first = AgentRuntime(
        challenge,
        _OneExperimentPlanner(),
        executor,
        _SupportedAnalyzer(),
        budget=RunBudget(max_steps=2, max_llm_calls=10),
        intelligence_store=store,
        initial_state=run_state,
        checkpoint_handler=_InterruptAfterExperimentResult(writer),
        experiment_orchestrator=orchestrator,
    )

    interrupted = first.run()
    restored = checkpoint.load()

    assert interrupted.status is RunStatus.FAILED
    assert restored.step_checkpoint is not None
    assert restored.step_checkpoint.stage == "experiment_result"
    assert restored.experiment_runtime_state is not None
    assert restored.experiment_runtime_state.records[0].status is ExperimentRuntimeStatus.COMPLETED
    assert executor.calls == 1
    assert len(restored.intelligence_store.state.evidence) == 1
    planner_context = ExperimentContextBuilder(
        restored.intelligence_store
    ).build(restored.experiment_runtime_state)
    assert planner_context["experiment_runtime"][0]["evaluation"] == "SUPPORTED"

    # Simulate the narrow per-file checkpoint gap: runtime state is terminal,
    # while step.json still advertises the preceding durable ToolResult stage.
    restored.step_checkpoint.stage = "tool_result"

    resumed_orchestrator = ExperimentOrchestrator(
        restored.intelligence_store,
        restored.experiment_runtime_state,
    )
    resumed_writer = RuntimeStepCheckpoint(
        checkpoint,
        restored.intelligence_store,
        artifacts_provider=lambda: restored.artifacts,
        experiment_runtime_provider=lambda: restored.experiment_runtime_state,
    )
    resumed = AgentRuntime(
        challenge,
        _OneExperimentPlanner(),
        executor,
        _SupportedAnalyzer(),
        budget=RunBudget(max_steps=2, max_llm_calls=10),
        intelligence_store=restored.intelligence_store,
        initial_state=restored.run_state,
        initial_step_checkpoint=restored.step_checkpoint,
        checkpoint_handler=resumed_writer,
        experiment_orchestrator=resumed_orchestrator,
        flag_confirmer=lambda candidate: candidate.value == "LOCAL_R101_RECOVERY_OK",
    ).run()

    assert resumed.status is RunStatus.SOLVED
    assert executor.calls == 1
    assert len(restored.intelligence_store.state.evidence) == 1
    completed = checkpoint.load()
    assert completed.step_checkpoint is not None
    assert completed.step_checkpoint.stage == "step_complete"
    assert (tmp_path / "checkpoint" / "experiment_runtime.json").is_file()

    cli_result = runner.invoke(
        app,
        ["experiment", "status", "--checkpoint", str(tmp_path / "checkpoint")],
    )
    assert cli_result.exit_code == 0
    assert "Experiment Runtime Status" in cli_result.stdout
    assert "COMPLETED" in cli_result.stdout
    assert "1 evidence" in cli_result.stdout
    assert "SUPPORTED" in cli_result.stdout


def test_normal_action_remains_backward_compatible_with_orchestrator():
    challenge = ChallengeSpec("r101-normal", "Normal", "authorized local fixture")
    store, state, orchestrator = _runtime_state(challenge, "run-r101-normal")

    class NormalPlanner:
        def plan(self, challenge, state, tool_schemas):
            del challenge, state, tool_schemas
            return ActionProposal(
                "read local data",
                "legacy normal action",
                [ToolCall("normal", "fake", {})],
            )

    class NormalExecutor:
        def execute(self, proposal):
            return [
                ToolResult(
                    "normal",
                    "fake",
                    True,
                    stdout="LOCAL_NORMAL_OK normal result",
                )
            ]

    class NormalAnalyzer:
        def analyze(self, observation, state):
            del observation, state
            return AnalysisResult(
                "legacy action completed",
                AnalysisOutcome.PROGRESS,
                flag_candidates=[
                    FlagCandidate("LOCAL_NORMAL_OK", "fake", 1.0, "normal result")
                ],
            )

    result = AgentRuntime(
        challenge,
        NormalPlanner(),
        NormalExecutor(),
        NormalAnalyzer(),
        intelligence_store=store,
        initial_state=RunState(challenge, run_id=state.run_id),
        experiment_orchestrator=orchestrator,
        flag_confirmer=lambda candidate: candidate.value == "LOCAL_NORMAL_OK",
    ).run()

    assert result.status is RunStatus.SOLVED
    assert state.records == []
