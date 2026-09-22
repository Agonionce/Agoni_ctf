from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agent.experience.extractor import ExperienceExtractor
from agent.experience.models import ExperienceRecord, ExperienceSecurityError
from agent.experience.retriever import ExperienceRetriever
from agent.experience.store import ExperienceStore
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.models import ExperimentStatus
from agent.intelligence.models import Credential, HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import ChallengeSpec, RunState, RunStatus
from agent.runtime.planner import JsonPlanner
from cli.app import app


runner = CliRunner()


def _completed_sql_run():
    challenge = ChallengeSpec(
        "r7-sql-first",
        "Fake local database challenge",
        "A fake SQL parameter returns a database syntax error.",
        category="web",
        authorization_scope="authorized_local_demo",
    )
    run_state = RunState(challenge, run_id="r7-test-run")
    run_state.status = RunStatus.SOLVED
    store = IntelligenceStore.create(challenge.challenge_id)
    store.add_credential(
        Credential(
            credential_type="test-only",
            value="DO_NOT_STORE_TEST_VALUE",
            location="synthetic fixture",
        )
    )
    manager = ExperimentManager(store)
    hypothesis = manager.create_hypothesis(
        "The id parameter may have SQL injection behavior",
        "web",
        0.5,
    )
    experiment = manager.create_experiment(
        hypothesis.id,
        "try a controlled UNION comparison after the database error",
        {
            "tool_name": "fake_local_web",
            "arguments": {"parameter": "id", "case": "union-comparison"},
        },
        "the fake SQL response changes",
    )
    manager.start_experiment(experiment.experiment_id)
    evidence = manager.record_evidence(
        experiment.experiment_id,
        source="fake response",
        observation="database syntax error observed",
    )
    manager.record_result(experiment.experiment_id, "UNION experiment failed")
    manager.close_experiment(experiment.experiment_id, ExperimentStatus.FAILED)
    manager.close_hypothesis(
        hypothesis.id,
        HypothesisStatus.CONFIRMED,
        [evidence.evidence_id],
    )
    return run_state, store


def _manual_record(
    *,
    record_id: str,
    domain: str,
    category: str,
    pattern: str,
) -> ExperienceRecord:
    return ExperienceRecord(
        id=record_id,
        domain=domain,
        category=category,
        trigger=f"Generic {category} signal appears.",
        pattern=pattern,
        strategy=f"Apply a controlled {category} comparison.",
        lesson=f"Treat {category} observations as evidence.",
        failure=f"Do not repeat an unsupported {category} attempt.",
        source_run=f"run-{record_id}",
        confidence=0.7,
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_rule_extractor_creates_generic_sql_experience_without_mutation():
    run_state, intelligence = _completed_sql_run()
    before = intelligence.state.to_dict()

    records = ExperienceExtractor().extract(run_state, intelligence.state)

    assert len(records) == 1
    record = records[0]
    assert record.domain == "web"
    assert record.category == "sql_injection"
    assert record.pattern == "Database behavior should be identified before payload selection."
    assert record.source_run == run_state.run_id
    assert record.confidence == pytest.approx(0.9)
    assert "DO_NOT_STORE_TEST_VALUE" not in json.dumps(record.to_dict())
    assert intelligence.state.to_dict() == before


def test_extractor_requires_a_completed_run_and_structured_experiment_evidence():
    run_state, intelligence = _completed_sql_run()
    run_state.status = RunStatus.RUNNING

    with pytest.raises(ValueError, match="completed run"):
        ExperienceExtractor().extract(run_state, intelligence.state)

    run_state.status = RunStatus.SOLVED
    assert ExperienceExtractor().extract(
        run_state,
        intelligence.state,
        experiment_history=[],
        evidence=[],
    ) == []


def test_store_add_list_get_query_and_json_persistence(tmp_path):
    path = tmp_path / "experiences" / "experience.json"
    store = ExperienceStore(path)
    sql_record = _manual_record(
        record_id="experience-sql",
        domain="web",
        category="sql_injection",
        pattern="Identify database behavior before payload selection.",
    )
    auth_record = _manual_record(
        record_id="experience-auth",
        domain="web",
        category="authentication",
        pattern="Map session behavior before bypass testing.",
    )

    store.add(sql_record)
    store.add(auth_record)
    assert store.add(sql_record) == sql_record
    assert store.get(sql_record.id) == sql_record
    assert store.query(category="sql_injection") == [sql_record]
    assert store.query(domain="web", keywords=["session"]) == [auth_record]

    restored = ExperienceStore(path)
    assert restored.list() == [sql_record, auth_record]
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1

    run_state, intelligence = _completed_sql_run()
    extracted_once = ExperienceExtractor().extract(run_state, intelligence.state)
    extracted_twice = ExperienceExtractor().extract(run_state, intelligence.state)
    extracted_store = ExperienceStore(tmp_path / "idempotent" / "experience.json")
    assert len(extracted_store.add_many(extracted_once)) == 1
    assert extracted_store.add_many(extracted_twice) == []


def test_retriever_matches_domain_category_skills_and_respects_limit(tmp_path):
    store = ExperienceStore(tmp_path / "experience.json")
    sql_record = _manual_record(
        record_id="experience-sql",
        domain="web",
        category="sql_injection",
        pattern="Identify SQL database behavior before payload selection.",
    )
    store.add(sql_record)
    store.add(
        _manual_record(
            record_id="experience-auth",
            domain="web",
            category="authentication",
            pattern="Map session behavior before bypass testing.",
        )
    )
    store.add(
        _manual_record(
            record_id="experience-crypto",
            domain="crypto",
            category="crypto_pattern",
            pattern="Classify a cipher before recovery.",
        )
    )
    challenge = ChallengeSpec(
        "r7-sql-second",
        "New SQL parameter",
        "A fake SQL response varies by parameter.",
        category="web",
    )

    context = ExperienceRetriever(store).retrieve(
        challenge,
        domain="web",
        skills=("sql_injection",),
        artifact_metadata=({"format": "fake-response"},),
        limit=1,
    )

    assert context.limit == 1
    assert len(context.relevant_experience) == 1
    assert context.relevant_experience[0]["id"] == sql_record.id


def test_planner_receives_bounded_experience_separately_from_intelligence(tmp_path):
    store = ExperienceStore(tmp_path / "experience.json")
    record = _manual_record(
        record_id="experience-sql",
        domain="web",
        category="sql_injection",
        pattern="Identify SQL database behavior before payload selection.",
    )
    store.add(record)
    challenge = ChallengeSpec("r7-planner", "SQL form", "SQL parameter", "web")
    context = ExperienceRetriever(store).retrieve(
        challenge,
        domain="web",
        skills=("sql_injection",),
        limit=1,
    ).to_dict()
    captured = {}

    def requester(_system_prompt, user_prompt):
        captured["prompt"] = user_prompt
        return {
            "objective": "inspect the fake SQL response",
            "reasoning_summary": "use one bounded local action",
            "actions": [{"tool_name": "fake", "arguments": {}}],
        }

    planner = JsonPlanner(
        requester,
        intelligence_context_provider=lambda _challenge, _state: {
            "facts": [{"content": "current-only-fact"}]
        },
        experience_context_provider=lambda _challenge, _state: context,
    )
    planner.plan(challenge, RunState(challenge), [])

    assert "current-only-fact" in captured["prompt"]
    assert record.pattern in captured["prompt"]
    assert "current-challenge intelligence" in captured["prompt"]
    assert "{experience_context}" not in captured["prompt"]


def test_experience_is_global_and_not_written_to_checkpoint(tmp_path):
    run_state, intelligence = _completed_sql_run()
    records = ExperienceExtractor().extract(run_state, intelligence.state)
    experience_path = tmp_path / "global" / "experience.json"
    ExperienceStore(experience_path).add_many(records)
    checkpoint_path = tmp_path / "checkpoint"
    IntelligenceCheckpoint(checkpoint_path).save(run_state, intelligence, [])

    assert experience_path.is_file()
    assert "experience.json" not in {item.name for item in checkpoint_path.iterdir()}
    assert "experiences" not in json.loads(
        (checkpoint_path / "intelligence.json").read_text(encoding="utf-8")
    )


def test_experience_record_rejects_target_specific_sensitive_values():
    with pytest.raises(ExperienceSecurityError, match="sensitive"):
        ExperienceRecord(
            id="experience-unsafe",
            domain="web",
            category="sql_injection",
            trigger="A generic SQL signal appears.",
            pattern="The answer is " + "flag" + "{SYNTHETIC_TEST_ONLY}.",
            strategy="Compare generic behavior.",
            lesson="Keep the result generic.",
            failure="Do not copy answers.",
            source_run="run-unsafe",
            confidence=0.5,
        )


@pytest.mark.parametrize(
    "private_text",
    [
        "HTB{candidate-value}",
        "Authorization: opaquecredential123456",
        "/Users/maxchen/private/app.py",
        r"C:\private\artifact.txt",
        r"\\server\share\artifact.txt",
        "Use HTTPRequestTool with arguments payload",
        "payload=private-request-body",
    ],
)
def test_experience_record_rejects_extended_private_values(private_text):
    with pytest.raises(ExperienceSecurityError, match="sensitive"):
        ExperienceRecord(
            id="experience-unsafe-extended",
            domain="web",
            category="authentication",
            trigger="A generic observation exists.",
            pattern="Compare a stable baseline.",
            strategy="Change one controlled variable.",
            lesson=private_text,
            failure="Do not copy target-specific values.",
            source_run="run-unsafe-extended",
            confidence=0.5,
        )


def test_experience_cli_lists_and_searches_global_json(tmp_path):
    path = tmp_path / "experiences" / "experience.json"
    ExperienceStore(path).add(
        _manual_record(
            record_id="experience-sql",
            domain="web",
            category="sql_injection",
            pattern="Identify SQL database behavior before payload selection.",
        )
    )

    listed = runner.invoke(app, ["experience", "list", "--store", str(path)])
    searched = runner.invoke(
        app,
        ["experience", "search", "sql", "--store", str(path)],
    )

    assert listed.exit_code == 0
    assert "Experience Memory" in listed.stdout
    assert "experience-sql" in listed.stdout.replace("\n", "")
    assert searched.exit_code == 0
    assert "Experience Search: sql" in searched.stdout
    assert "experience-sql" in searched.stdout.replace("\n", "")
