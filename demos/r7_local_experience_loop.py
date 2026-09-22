"""R7 two-challenge local experience-memory demo; no Tool or network access."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from agent.experience.extractor import ExperienceExtractor
from agent.experience.retriever import ExperienceRetriever
from agent.experience.store import ExperienceStore
from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.models import ExperimentStatus
from agent.intelligence.models import HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import ChallengeSpec, RunState, RunStatus


CREATE_TOKEN = "LOCAL_EXPERIENCE_CREATE_OK"
RETRIEVE_TOKEN = "LOCAL_EXPERIENCE_RETRIEVE_OK"
LOOP_TOKEN = "LOCAL_EXPERIENCE_LOOP_OK"


def run_demo(root: str | Path) -> tuple[str, str, str]:
    """Create reusable SQL experience, then retrieve it for a second challenge."""

    root_path = Path(root)
    first_challenge = ChallengeSpec(
        challenge_id="r7-fake-sql-first",
        title="Fake local SQL behavior challenge",
        description="A fake id parameter produces a database syntax error.",
        category="web",
        authorization_scope="authorized_local_demo",
    )
    first_run = RunState(first_challenge, run_id="r7-local-run-first")
    first_run.status = RunStatus.SOLVED
    intelligence = IntelligenceStore.create(first_challenge.challenge_id)
    manager = ExperimentManager(intelligence)
    hypothesis = manager.create_hypothesis(
        "The fake id parameter may expose SQL injection behavior",
        "web",
        0.5,
    )
    experiment = manager.create_experiment(
        hypothesis.id,
        "test whether a UNION-style comparison changes the fake response",
        {
            "tool_name": "fake_local_web",
            "arguments": {"parameter": "id", "test_case": "union-comparison"},
        },
        "the fake database response changes in a controlled way",
    )
    manager.start_experiment(experiment.experiment_id)
    evidence = manager.record_evidence(
        experiment.experiment_id,
        source="fake local response",
        observation="database syntax error observed before the UNION experiment",
    )
    manager.record_result(
        experiment.experiment_id,
        "UNION experiment failed because the fake filter returned a different response",
    )
    manager.close_experiment(experiment.experiment_id, ExperimentStatus.FAILED)
    manager.close_hypothesis(
        hypothesis.id,
        HypothesisStatus.CONFIRMED,
        [evidence.evidence_id],
    )

    state_before_extraction = intelligence.state.to_dict()
    extracted = ExperienceExtractor().extract(first_run, intelligence.state)
    if not extracted or extracted[0].category != "sql_injection":
        raise RuntimeError("the fake SQL run did not produce reusable experience")
    experience_store = ExperienceStore(root_path / "experiences" / "experience.json")
    experience_store.add_many(extracted)
    if intelligence.state.to_dict() != state_before_extraction:
        raise RuntimeError("experience extraction mutated current-challenge intelligence")

    second_challenge = ChallengeSpec(
        challenge_id="r7-fake-sql-second",
        title="New fake local SQL parameter challenge",
        description="Compare SQL-like behavior for a different fake parameter.",
        category="web",
        authorization_scope="authorized_local_demo",
    )
    retrieved = ExperienceRetriever(experience_store).retrieve(
        second_challenge,
        domain="web",
        skills=("sql_injection",),
        artifact_metadata=({"format": "fake-local-response"},),
        limit=3,
    )
    if not retrieved.relevant_experience:
        raise RuntimeError("the second fake challenge did not retrieve prior experience")
    if retrieved.relevant_experience[0]["category"] != "sql_injection":
        raise RuntimeError("the retrieved experience was not the prior SQL pattern")
    return CREATE_TOKEN, RETRIEVE_TOKEN, LOOP_TOKEN


if __name__ == "__main__":
    with TemporaryDirectory(prefix="agonionce-r7-") as directory:
        for token in run_demo(Path(directory)):
            print(token)
