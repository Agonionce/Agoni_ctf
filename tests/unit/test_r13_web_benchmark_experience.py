from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agent.completion.lessons import LessonExtractor, LessonKind
from agent.completion.models import ChallengeReport
from agent.domains.web.benchmark import (
    WebBenchmarkLoader,
    WebBenchmarkReportBuilder,
    WebBenchmarkRunner,
    WebBenchmarkRunSnapshot,
)
from agent.experience.models import ExperienceRecord
from agent.experience.quality import (
    ExperienceFeedbackManager,
    ExperienceFeedbackOutcome,
    ExperienceQualityStore,
)
from agent.experience.retriever import ExperienceRetriever
from agent.experience.store import ExperienceStore
from agent.runtime.contracts import ChallengeSpec
from cli.app import app


runner = CliRunner()
BENCHMARK_ROOT = Path(__file__).resolve().parents[2] / "benchmarks" / "web"


def _experience(path: Path) -> tuple[ExperienceStore, ExperienceRecord, ExperienceQualityStore]:
    store = ExperienceStore(path)
    record = store.add(ExperienceRecord(
        id="experience-r13-test",
        domain="web",
        category="authentication",
        trigger="An authentication boundary is observed.",
        pattern="Compare access state before interpreting behavior.",
        strategy="Record one bounded baseline for each permitted state.",
        lesson="Keep authentication evidence separate from conclusions.",
        failure="Do not repeat an unsupported comparison without new evidence.",
        source_run="source-r13-test",
        confidence=0.7,
    ))
    quality = ExperienceQualityStore.for_experience_path(path)
    return store, record, quality


def _snapshot(run_id: str, solved: bool, experience_id: str = "") -> WebBenchmarkRunSnapshot:
    return WebBenchmarkRunSnapshot(
        run_id=run_id,
        result="SOLVED" if solved else "FAILED",
        solved=solved,
        experiments=({"experiment_id": "experiment-1", "status": "SUCCESS"},),
        evidence=tuple({"evidence_id": f"evidence-{index}"} for index in range(4)),
        hypotheses=({"id": "hypothesis-1", "status": "CONFIRMED"},),
        tool_usage={"fake_local_web": 2},
        experience_usage=(experience_id,) if experience_id else (),
        duration_seconds=0.25,
    )


def test_r13_benchmark_catalog_covers_required_categories_and_evaluation_contract():
    cases = WebBenchmarkLoader(BENCHMARK_ROOT).list()
    categories = {item.category for item in cases}

    assert {
        "authentication", "authorization", "parameter_behavior", "session",
        "file_processing", "api_behavior", "business_logic",
    } <= categories
    assert all(item.evaluation["solved_when"] == "all_expectations_pass" for item in cases)
    assert all(item.environment["network"] == "disabled" for item in cases)


def test_evaluation_record_contains_run_research_and_usage_data(tmp_path):
    loader = WebBenchmarkLoader(BENCHMARK_ROOT)
    snapshot = _snapshot("run-r13-evaluation", True, "experience-r13-test")
    result = WebBenchmarkRunner(loader).run(
        loader.load("authentication"),
        result_root=tmp_path,
        run_snapshot=snapshot,
    )
    evaluation = result.evaluation

    assert result.passed
    assert evaluation is not None
    assert evaluation.challenge_metadata["category"] == "authentication"
    assert evaluation.solved
    assert len(evaluation.experiments) == 1
    assert len(evaluation.evidence) == 4
    assert len(evaluation.hypotheses) == 1
    assert evaluation.tool_usage == {"fake_local_web": 2}
    assert evaluation.experience_usage == ("experience-r13-test",)
    assert evaluation.duration_seconds == 0.25
    assert (tmp_path / "authentication.json").is_file()
    assert list((tmp_path / "history" / "authentication").glob("*.json"))


def test_performance_report_aggregates_success_experiments_experience_and_trend(tmp_path):
    loader = WebBenchmarkLoader(BENCHMARK_ROOT)
    benchmark_runner = WebBenchmarkRunner(loader)
    case = loader.load("authentication")
    benchmark_runner.run(case, result_root=tmp_path, run_snapshot=_snapshot("run-r13-fail", False))
    benchmark_runner.run(
        case,
        result_root=tmp_path,
        run_snapshot=_snapshot("run-r13-pass", True, "experience-r13-test"),
    )
    report = WebBenchmarkReportBuilder().from_directory(tmp_path)

    assert report.total_challenges == 1
    assert report.total_runs == 2
    assert report.solved_runs == 1
    assert report.success_rate == 0.5
    assert report.average_experiments == 1.0
    assert report.total_tool_calls == 4
    assert report.experience_usage_count == 1
    assert report.improvement_trend == "IMPROVING"


def test_experience_feedback_updates_effectiveness_confidence_and_is_idempotent(tmp_path):
    store, experience, quality_store = _experience(tmp_path / "global" / "experience.json")
    manager = ExperienceFeedbackManager(store, quality_store)
    successful = manager.record(
        experience.id,
        source_run="run-r13-success",
        source_challenge="challenge-r13-success",
        outcome=ExperienceFeedbackOutcome.SUCCESS,
        solved=True,
        evidence_refs=("evidence-r13-success",),
    )
    successful_confidence = successful.confidence
    manager.record(
        experience.id,
        source_run="run-r13-success",
        source_challenge="challenge-r13-success",
        outcome=ExperienceFeedbackOutcome.SUCCESS,
        solved=True,
        evidence_refs=("evidence-r13-success",),
    )
    final = manager.record(
        experience.id,
        source_run="run-r13-failure",
        source_challenge="challenge-r13-failure",
        outcome=ExperienceFeedbackOutcome.FAILURE,
        solved=False,
        evidence_refs=("evidence-r13-failure",),
    )

    assert successful_confidence > experience.confidence
    assert final.use_count == 2
    assert final.validation_count == 2
    assert final.success_count == 1 and final.failure_count == 1
    assert final.effectiveness == 0.5
    restored = ExperienceQualityStore.for_experience_path(store.path).get(experience.id)
    assert restored is not None and restored.use_count == 2
    assert len(ExperienceQualityStore.for_experience_path(store.path).feedback()) == 2


def test_experience_quality_is_injected_into_bounded_retrieval(tmp_path):
    store, experience, quality = _experience(tmp_path / "experience.json")
    ExperienceFeedbackManager(store, quality).record(
        experience.id,
        source_run="run-r13-retrieval",
        source_challenge="challenge-r13-retrieval",
        outcome=ExperienceFeedbackOutcome.SUCCESS,
        solved=True,
    )
    context = ExperienceRetriever(store, quality).retrieve(
        ChallengeSpec(
            "challenge-r13-next",
            "Authentication state",
            "Compare a local authentication boundary.",
            category="web",
        ),
        limit=1,
    )

    assert context.relevant_experience[0]["id"] == experience.id
    assert context.relevant_experience[0]["quality"]["use_count"] == 1
    assert context.relevant_experience[0]["quality"]["effectiveness"] == 1.0


def test_lesson_extractor_separates_success_failure_and_general_insight():
    report = ChallengeReport(
        challenge_id="challenge-r13-lessons",
        summary="A local Web research run completed.",
        domain="web",
        status="COMPLETED",
        key_findings=({
            "title": "Authorization state difference",
            "description": "Two captured states differed.",
            "artifact_refs": [{"artifact_id": "artifact-r13-finding"}],
        },),
        experiments=(
            {"experiment_id": "experiment-success", "goal": "compare access state", "status": "SUCCESS"},
            {"experiment_id": "experiment-failure", "goal": "compare an unsupported path", "status": "FAILED"},
        ),
        artifacts=(),
        evidence=(
            {
                "evidence_id": "evidence-success",
                "experiment_id": "experiment-success",
                "artifact_refs": [{"artifact_id": "artifact-success"}],
            },
            {
                "evidence_id": "evidence-failure",
                "experiment_id": "experiment-failure",
                "artifact_refs": [{"artifact_id": "artifact-failure"}],
            },
        ),
    )
    lessons = LessonExtractor().extract(report)

    assert {item.kind for item in lessons} == {
        LessonKind.SUCCESSFUL_STRATEGY,
        LessonKind.FAILED_STRATEGY,
        LessonKind.GENERAL_INSIGHT,
    }
    success = next(item for item in lessons if item.kind is LessonKind.SUCCESSFUL_STRATEGY)
    assert "evidence-success" in success.evidence_refs
    assert "artifact-success" in success.evidence_refs
    assert success.experiment_refs == ("experiment-success",)


def test_r13_benchmark_report_and_experience_feedback_cli(tmp_path):
    result_dir = tmp_path / "results"
    benchmark = runner.invoke(app, [
        "benchmark", "run", "authentication",
        "--root", str(BENCHMARK_ROOT),
        "--result-dir", str(result_dir),
    ])
    report = runner.invoke(app, [
        "benchmark", "report", "--result-dir", str(result_dir),
    ])
    store, experience, _quality = _experience(tmp_path / "global" / "experience.json")
    feedback = runner.invoke(app, [
        "experience", "feedback", experience.id,
        "--outcome", "SUCCESS",
        "--source-run", "run-r13-cli",
        "--source-challenge", "challenge-r13-cli",
        "--solved",
        "--evidence", "evidence-r13-cli",
        "--store", str(store.path),
    ])
    quality = runner.invoke(app, [
        "experience", "quality", experience.id,
        "--store", str(store.path),
    ])

    assert benchmark.exit_code == 0
    assert report.exit_code == 0 and "Success rate" in report.stdout
    assert feedback.exit_code == 0 and "effectiveness=1.00" in feedback.stdout
    assert quality.exit_code == 0 and experience.id in quality.stdout
    assert json.loads((result_dir / "authentication.json").read_text())["schema_version"] == 2
