from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.experiment.context import ExperimentContextBuilder
from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.models import ExperimentStatus
from agent.intelligence.models import ArtifactReference, HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import ChallengeSpec, RunState
from agent.runtime.planner import JsonPlanner
from cli.app import app


runner = CliRunner()


def _completed_experiment(store: IntelligenceStore):
    manager = ExperimentManager(store)
    hypothesis = manager.create_hypothesis(
        "id parameter may be SQL injectable",
        "web",
        0.5,
    )
    experiment = manager.create_experiment(
        hypothesis.id,
        "compare a controlled predicate",
        {"tool_name": "fake_local_web", "arguments": {"id": "1 AND 1=2"}},
        "response differs from the SQL-error baseline",
    )
    assert experiment.status is ExperimentStatus.PROPOSED
    manager.start_experiment(experiment.experiment_id)
    assert experiment.status is ExperimentStatus.RUNNING
    evidence = manager.record_evidence(
        experiment.experiment_id,
        source="fake ToolResult stdout",
        observation="response changed to No rows matched",
        artifact_refs=[ArtifactReference("artifact-001", "evidence_for")],
    )
    manager.record_result(experiment.experiment_id, "No rows matched")
    manager.close_experiment(experiment.experiment_id, ExperimentStatus.SUCCESS)
    manager.close_hypothesis(
        hypothesis.id,
        HypothesisStatus.CONFIRMED,
        [evidence.evidence_id],
    )
    return hypothesis, experiment, evidence


def test_hypothesis_experiment_and_evidence_lifecycle():
    store = IntelligenceStore.create("r6-lifecycle")

    hypothesis, experiment, evidence = _completed_experiment(store)

    assert hypothesis.status is HypothesisStatus.CONFIRMED
    assert hypothesis.confidence == 1.0
    assert hypothesis.evidence_refs == [evidence.evidence_id]
    assert experiment.status is ExperimentStatus.SUCCESS
    assert experiment.actual_result == "No rows matched"
    assert evidence.observation == "response changed to No rows matched"
    assert not hasattr(evidence, "conclusion")
    assert any(
        link.entity_type == "evidence"
        and link.entity_id == evidence.evidence_id
        and link.artifact_id == "artifact-001"
        for link in store.state.artifact_links
    )


def test_invalid_lifecycle_transitions_fail_closed():
    store = IntelligenceStore.create("r6-invalid")
    manager = ExperimentManager(store)
    hypothesis = manager.create_hypothesis("test an input", "web")
    experiment = manager.create_experiment(
        hypothesis.id,
        "test one input",
        {"tool_name": "fake", "arguments": {}},
        "response changes",
    )

    with pytest.raises(ValueError, match="RUNNING"):
        manager.record_result(experiment.experiment_id, "too early")
    manager.start_experiment(experiment.experiment_id)
    evidence = manager.record_evidence(
        experiment.experiment_id,
        source="fake",
        observation="observed before close",
    )
    with pytest.raises(ValueError, match="closed experiment"):
        manager.close_hypothesis(
            hypothesis.id,
            HypothesisStatus.CONFIRMED,
            [evidence.evidence_id],
        )
    manager.record_result(experiment.experiment_id, "observed")
    with pytest.raises(ValueError, match="SUCCESS or FAILED"):
        manager.close_experiment(experiment.experiment_id, ExperimentStatus.PROPOSED)
    with pytest.raises(ValueError, match="requires evidence"):
        manager.close_hypothesis(hypothesis.id, HypothesisStatus.CONFIRMED, [])


def test_checkpoint_restores_consistent_experiment_state(tmp_path):
    challenge = ChallengeSpec(
        "r6-checkpoint",
        "Fake Web",
        "authorized local fake challenge",
        category="web",
    )
    store = IntelligenceStore.create(challenge.challenge_id)
    hypothesis, experiment, evidence = _completed_experiment(store)
    checkpoint_dir = tmp_path / "checkpoint"
    checkpoint = IntelligenceCheckpoint(checkpoint_dir)
    checkpoint.save(
        RunState(challenge),
        store,
        [{"artifact_id": "artifact-001", "path": "work/fake-response.txt"}],
    )

    restored = checkpoint.load().intelligence_store

    assert (checkpoint_dir / "experiments.json").is_file()
    assert restored.get_hypothesis(hypothesis.id).status is HypothesisStatus.CONFIRMED
    assert restored.get_experiment(experiment.experiment_id).status is ExperimentStatus.SUCCESS
    assert restored.get_evidence(evidence.evidence_id).artifact_refs[0].artifact_id == "artifact-001"

    raw = json.loads((checkpoint_dir / "experiments.json").read_text(encoding="utf-8"))
    raw["experiments"][0]["actual_result"] = "tampered"
    (checkpoint_dir / "experiments.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="inconsistent"):
        checkpoint.load()


def test_planner_experiment_context_is_bounded():
    store = IntelligenceStore.create("r6-context")
    manager = ExperimentManager(store)
    for index in range(4):
        hypothesis = manager.create_hypothesis(f"hypothesis-{index}", "web")
        experiment = manager.create_experiment(
            hypothesis.id,
            f"experiment-{index}",
            {"tool_name": "fake", "arguments": {"index": index}},
            f"expected-{index}",
        )
        manager.start_experiment(experiment.experiment_id)
        manager.record_evidence(
            experiment.experiment_id,
            source="fake",
            observation=f"evidence-{index}",
        )
        manager.record_result(experiment.experiment_id, f"actual-{index}")
        manager.close_experiment(experiment.experiment_id, ExperimentStatus.SUCCESS)
    builder = ExperimentContextBuilder(
        store,
        hypothesis_limit=2,
        experiment_limit=2,
        evidence_limit=2,
    )
    context = builder.build()
    captured = {}

    def requester(_system_prompt, user_prompt):
        captured["prompt"] = user_prompt
        return {
            "objective": "inspect bounded evidence",
            "reasoning_summary": "select one controlled fake action",
            "actions": [{"tool_name": "fake", "arguments": {}}],
        }

    challenge = ChallengeSpec("r6-context", "Fake Web", "local experiment", "web")
    planner = JsonPlanner(
        requester,
        experiment_context_provider=lambda _challenge, _state: context,
    )
    planner.plan(challenge, RunState(challenge), [])

    assert len(context["current_hypotheses"]) == 2
    assert len(context["recent_experiments"]) == 2
    assert len(context["evidence_summary"]) == 2
    assert "hypothesis-3" in captured["prompt"]
    assert '"statement": "hypothesis-0"' not in captured["prompt"]
    assert "evidence is not a conclusion" in captured["prompt"]
    assert "{experiment_context}" not in captured["prompt"]


def test_r6_read_only_cli_lists_checkpoint_state(tmp_path):
    challenge = ChallengeSpec("r6-cli", "Fake Web", "authorized local fake challenge")
    store = IntelligenceStore.create(challenge.challenge_id)
    _completed_experiment(store)
    checkpoint_dir = tmp_path / "checkpoint"
    IntelligenceCheckpoint(checkpoint_dir).save(
        RunState(challenge),
        store,
        [{"artifact_id": "artifact-001", "path": "work/fake-response.txt"}],
    )

    experiment_result = runner.invoke(
        app,
        ["experiment", "list", "--checkpoint", str(checkpoint_dir)],
    )
    hypothesis_result = runner.invoke(
        app,
        ["hypothesis", "list", "--checkpoint", str(checkpoint_dir)],
    )
    evidence_result = runner.invoke(
        app,
        ["evidence", "list", "--checkpoint", str(checkpoint_dir)],
    )

    assert experiment_result.exit_code == 0
    assert "Experiments" in experiment_result.stdout
    assert "SUCCESS" in experiment_result.stdout
    assert hypothesis_result.exit_code == 0
    assert "Hypotheses" in hypothesis_result.stdout
    assert "CONFIRMED" in hypothesis_result.stdout
    assert evidence_result.exit_code == 0
    assert "Evidence" in evidence_result.stdout
    assert "artifact-001" in evidence_result.stdout
