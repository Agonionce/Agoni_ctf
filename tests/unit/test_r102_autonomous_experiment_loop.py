from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from agent.domains.manager import build_default_runtime_manager
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.models import EvidenceRecord, ExperimentStatus
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluation,
    ExperimentEvaluationStatus,
    ExperimentRuntimeRecord,
    ExperimentRuntimeState,
    ExperimentRuntimeStatus,
)
from agent.intelligence.experiment.runtime.feedback import ExperimentFeedbackManager
from agent.intelligence.experiment.runtime.loop import AutonomousExperimentLoop
from agent.intelligence.experiment.runtime.research import (
    DomainExperimentAdapter,
    ExperimentPrioritizer,
    HypothesisCandidate,
)
from agent.intelligence.models import (
    ArtifactReference,
    HypothesisSource,
    HypothesisStatus,
    KnowledgeUpdateSuggestion,
    OpenQuestion,
    Priority,
)
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import (
    ActionProposal,
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    Observation,
    RunState,
    ToolCall,
    ToolResult,
)
from cli.app import app


runner = CliRunner()


def _observation(step: int = 1) -> Observation:
    proposal = ActionProposal(
        "observe local fixture",
        "collect bounded evidence",
        [ToolCall(f"call-{step}", "fake", {})],
    )
    return Observation(
        step,
        proposal.objective,
        proposal,
        [
            ToolResult(
                f"call-{step}",
                "fake",
                True,
                stdout="parameter response changed",
                artifact_refs=[f"artifact-{step}"],
            )
        ],
        observation_id=f"observation-{step}",
    )


def _analysis() -> AnalysisResult:
    return AnalysisResult(
        "an endpoint parameter is available for comparison",
        AnalysisOutcome.PROGRESS,
        confidence=0.8,
        knowledge_updates=[
            KnowledgeUpdateSuggestion(
                "hypothesis",
                {
                    "statement": "Parameter id affects response behavior.",
                    "domain": "web",
                    "confidence": 0.6,
                    "priority": "HIGH",
                    "experiment_goal": "compare bounded parameter responses",
                    "expected_result": "response changed",
                },
                artifact_refs=[
                    ArtifactReference("artifact-1", "hypothesis_source")
                ],
            )
        ],
    )


def _web_loop(*, with_experience: bool = False):
    challenge = ChallengeSpec(
        "r102-unit",
        "R10.2 Unit",
        "authorized fake local web challenge",
        category="web",
        metadata={"entry_points": ["/item"]},
    )
    store = IntelligenceStore.create(challenge.challenge_id)
    state = ExperimentRuntimeState("run-r102-unit", challenge.challenge_id)
    manager = build_default_runtime_manager()
    manager.initialize("web", challenge)
    experience = (
        {
            "relevant_experience": [
                {
                    "id": "experience-previous",
                    "domain": "web",
                    "category": "behavior_comparison",
                    "trigger": "parameter response",
                    "pattern": "compare responses before deciding",
                    "strategy": "compare bounded parameter responses",
                    "lesson": "preserve response artifacts",
                    "confidence": 0.8,
                }
            ]
        }
        if with_experience
        else {}
    )
    loop = AutonomousExperimentLoop(
        store,
        state,
        domain_manager=manager,
        experience_context_provider=lambda: experience,
    )
    return challenge, store, state, manager, loop


def test_hypothesis_generation_uses_multiple_bounded_sources():
    _, store, state, _, loop = _web_loop(with_experience=True)
    store.add_open_question(OpenQuestion("Does the parameter alter the response?"))

    decision = loop.advance(_observation(), _analysis())

    sources = {item.source for item in state.active_candidates}
    assert HypothesisSource.ANALYZER in sources
    assert HypothesisSource.INTELLIGENCE in sources
    assert HypothesisSource.EXPERIENCE in sources
    assert decision.decision == "PROPOSE_EXPERIMENT"
    analyzer = next(
        item
        for item in state.active_candidates
        if item.statement == "Parameter id affects response behavior."
    )
    hypothesis = store.get_hypothesis(analyzer.hypothesis_id)
    assert hypothesis is not None
    assert hypothesis.source is HypothesisSource.ANALYZER
    assert hypothesis.priority is Priority.HIGH
    assert hypothesis.related_artifacts[0].artifact_id == "artifact-1"


def test_experiment_priority_penalizes_previous_failed_experiments():
    repeated = HypothesisCandidate(
        "Repeated hypothesis",
        "web",
        HypothesisSource.ANALYZER,
        0.8,
        Priority.HIGH,
        "repeat the same experiment",
        "response changed",
        hypothesis_id="hyp-repeated",
        evidence_value=0.8,
    )
    fresh = HypothesisCandidate(
        "Fresh phase hypothesis",
        "web",
        HypothesisSource.DOMAIN_RUNTIME,
        0.7,
        Priority.HIGH,
        "collect a distinct observable",
        "new evidence recorded",
        hypothesis_id="hyp-fresh",
        evidence_value=0.8,
    )
    failed = SimpleNamespace(
        hypothesis_id="hyp-repeated",
        status=SimpleNamespace(value="FAILED"),
        evaluation=None,
    )

    ranked = ExperimentPrioritizer().rank(
        [repeated, fresh],
        phase="ANALYSIS",
        runtime_records=[failed, failed],
    )

    assert ranked[0] is fresh
    assert repeated.score < fresh.score
    assert "previous-failures=2" in repeated.priority_reasons


@pytest.mark.parametrize(
    ("evaluation_status", "expected_status", "has_follow_up", "has_failure"),
    [
        (ExperimentEvaluationStatus.SUPPORTED, HypothesisStatus.SUPPORTED, False, False),
        (ExperimentEvaluationStatus.CONTRADICTED, HypothesisStatus.REJECTED, False, True),
        (ExperimentEvaluationStatus.INCONCLUSIVE, HypothesisStatus.OPEN, True, False),
    ],
)
def test_evaluation_feedback_updates_intelligence_and_domain_context(
    evaluation_status,
    expected_status,
    has_follow_up,
    has_failure,
):
    challenge, store, _, manager, _ = _web_loop()
    experiment_manager = ExperimentManager(store)
    hypothesis = experiment_manager.create_hypothesis(
        "Parameter id affects response behavior.",
        "web",
        0.5,
        source=HypothesisSource.ANALYZER,
    )
    experiment = experiment_manager.create_experiment(
        hypothesis.id,
        "compare response behavior",
        {"tool_name": "fake", "arguments": {}},
        "response changed",
    )
    experiment_manager.start_experiment(experiment.experiment_id)
    evidence = store.add_evidence(
        EvidenceRecord(
            source="ToolResult:fake:call-1",
            observation="response changed",
            artifact_refs=[ArtifactReference("artifact-feedback", "evidence_for")],
            experiment_id=experiment.experiment_id,
            hypothesis_id=hypothesis.id,
            observation_id="observation-feedback",
        )
    )
    experiment_manager.record_result(experiment.experiment_id, "response observed")
    experiment_manager.close_experiment(experiment.experiment_id, ExperimentStatus.SUCCESS)
    record = ExperimentRuntimeRecord(
        "run-r102-unit",
        challenge.challenge_id,
        1,
        "call-1",
        hypothesis.id,
        experiment.experiment_id,
        "a" * 64,
        {"objective": "test"},
        status=ExperimentRuntimeStatus.COMPLETED,
        observation_id="observation-feedback",
        evidence_ids=[evidence.evidence_id],
    )
    evaluation = ExperimentEvaluation(
        experiment.experiment_id,
        evaluation_status,
        "Deterministic fixture evaluation.",
        (evidence.evidence_id,),
    )

    feedback = ExperimentFeedbackManager(
        store,
        domain_manager=manager,
    ).apply(record, evaluation)

    assert store.get_hypothesis(hypothesis.id).status is expected_status
    assert bool(feedback.next_experiment_goal) is has_follow_up
    assert bool(feedback.failed_attempt_id) is has_failure
    assert manager.current_state.details["experiment_feedback"][0][
        "evaluation"
    ] == evaluation_status.value


def test_domain_runtime_integration_exposes_reasoning_hints_not_tools():
    _, _, _, manager, _ = _web_loop()
    context = DomainExperimentAdapter().build_context(manager)

    assert context["domain"] == "web"
    assert context["phase"] == "RECON"
    assert context["hypothesis_candidates"]
    serialized = str(context).lower()
    assert "tool_name" not in serialized
    assert "arguments" not in serialized


def test_experience_influence_is_recorded_without_global_memory_write():
    _, store, state, _, loop = _web_loop(with_experience=True)

    decision = loop.advance(_observation(), _analysis())

    selected = store.get_hypothesis(decision.hypothesis_id)
    assert selected is not None
    assert "experience-previous" in selected.experience_influence
    assert "experience-previous" in decision.experience_influence


def test_checkpoint_restores_loop_state_and_cli_views(tmp_path):
    challenge, store, state, manager, loop = _web_loop(with_experience=True)
    loop.advance(_observation(), _analysis())
    checkpoint_dir = tmp_path / "checkpoint"
    IntelligenceCheckpoint(checkpoint_dir).save(
        RunState(challenge, run_id=state.run_id),
        store,
        [{"artifact_id": "artifact-1", "path": "output/fake.json"}],
        manager.current_state,
        state,
    )

    restored = IntelligenceCheckpoint(checkpoint_dir).load()

    assert restored.experiment_runtime_state is not None
    assert restored.experiment_runtime_state.loop_iteration == 1
    assert restored.experiment_runtime_state.active_hypothesis_ids
    assert restored.experiment_runtime_state.active_candidates
    assert len(restored.experiment_runtime_state.decision_history) == 1
    restored_manager = build_default_runtime_manager()
    restored_manager.initialize(
        "web",
        challenge,
        restored.domain_runtime_state,
    )
    resumed_loop = AutonomousExperimentLoop(
        restored.intelligence_store,
        restored.experiment_runtime_state,
        domain_manager=restored_manager,
    )
    resumed_loop.advance(
        _observation(2),
        AnalysisResult(
            "restored loop received the next local observation",
            AnalysisOutcome.PROGRESS,
            confidence=0.6,
        ),
    )
    assert restored.experiment_runtime_state.loop_iteration == 2
    assert len(restored.experiment_runtime_state.decision_history) == 2
    loop_result = runner.invoke(
        app,
        ["experiment", "loop", "--checkpoint", str(checkpoint_dir)],
    )
    history_result = runner.invoke(
        app,
        ["experiment", "history", "--checkpoint", str(checkpoint_dir)],
    )
    hypothesis_result = runner.invoke(
        app,
        ["hypothesis", "list", "--checkpoint", str(checkpoint_dir)],
    )
    assert loop_result.exit_code == 0
    assert "Autonomous Experiment Loop" in loop_result.stdout
    assert history_result.exit_code == 0
    assert "Experiment History" in history_result.stdout
    assert hypothesis_result.exit_code == 0
    assert "Hypotheses" in hypothesis_result.stdout
    assert "Source" in hypothesis_result.stdout


def test_legacy_r101_experiment_runtime_checkpoint_remains_loadable():
    legacy = {
        "schema_version": 1,
        "run_id": "legacy-run",
        "challenge_id": "legacy-challenge",
        "current_experiments": [],
        "pending_experiments": [],
        "evaluation_results": {},
        "updated_at": "2026-01-01T00:00:00+00:00",
    }

    restored = ExperimentRuntimeState.from_dict(legacy)

    assert restored.loop_iteration == 0
    assert restored.active_candidates == []
    assert restored.decision_history == []
