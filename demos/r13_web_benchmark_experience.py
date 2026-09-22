"""R13 fake-local benchmark evaluation and Experience feedback demo."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.completion.lessons import LessonExtractor, LessonKind
from agent.completion.models import ChallengeReport
from agent.domains.web.benchmark import (
    WebBenchmarkLoader,
    WebBenchmarkReportBuilder,
    WebBenchmarkRunner,
    WebBenchmarkRunSnapshot,
)
from agent.experience.models import ExperienceRecord
from agent.experience.quality import ExperienceQualityStore
from agent.experience.store import ExperienceStore


def _snapshot(run_id: str, *, solved: bool, experience_id: str) -> WebBenchmarkRunSnapshot:
    return WebBenchmarkRunSnapshot(
        run_id=run_id,
        result="SOLVED" if solved else "FAILED",
        solved=solved,
        experiments=({
            "experiment_id": f"experiment-{run_id}",
            "goal": "compare bounded authentication behavior",
            "status": "SUCCESS" if solved else "FAILED",
        },),
        evidence=tuple({
            "evidence_id": f"evidence-{run_id}-{index}",
            "source": "fake-local benchmark",
            "observation": "bounded benchmark observation",
        } for index in range(4)),
        hypotheses=({
            "id": f"hypothesis-{run_id}",
            "statement": "Authentication state affects the observed local response.",
            "status": "CONFIRMED" if solved else "OPEN",
        },),
        tool_usage={"fake_local_web": 1},
        experience_usage=(experience_id,),
        duration_seconds=0.1,
    )


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    loader = WebBenchmarkLoader(repository / "benchmarks" / "web")
    with TemporaryDirectory(prefix="agonionce-r13-") as temporary:
        root = Path(temporary)
        result_root = root / "benchmark-results"
        experience_path = root / "global" / "experience.json"
        experience_store = ExperienceStore(experience_path)
        experience = experience_store.add(ExperienceRecord(
            id="experience-r13-local",
            domain="web",
            category="authentication",
            trigger="An authentication boundary is observed.",
            pattern="Compare access state before interpreting protected behavior.",
            strategy="Record a bounded baseline for each permitted state.",
            lesson="Keep authentication evidence separate from conclusions.",
            failure="Do not repeat an unsupported comparison without new evidence.",
            source_run="r13-approved-source",
            confidence=0.7,
        ))
        quality_store = ExperienceQualityStore.for_experience_path(experience_path)
        quality_store.ensure(
            experience,
            source_challenge="r13-approved-source",
            source_evidence=("evidence-approved-source",),
        )
        runner = WebBenchmarkRunner(loader)
        authentication = loader.load("authentication")
        runner.run(
            authentication,
            result_root=result_root,
            run_snapshot=_snapshot(
                "run-r13-success",
                solved=True,
                experience_id=experience.id,
            ),
            experience_store=experience_store,
            quality_store=quality_store,
            apply_experience_feedback=True,
        )
        runner.run(
            authentication,
            result_root=result_root,
            run_snapshot=_snapshot(
                "run-r13-failure",
                solved=False,
                experience_id=experience.id,
            ),
            experience_store=experience_store,
            quality_store=quality_store,
            apply_experience_feedback=True,
        )
        for case in loader.list():
            if case.benchmark_id != "authentication":
                assert runner.run(case, result_root=result_root).passed
        performance = WebBenchmarkReportBuilder().from_directory(result_root)
        assert performance.total_challenges == len(loader.list())
        assert performance.total_runs == len(loader.list()) + 1
        assert performance.experience_usage_count == 2
        quality = quality_store.get(experience.id)
        assert quality is not None
        assert quality.use_count == 2
        assert quality.success_count == 1 and quality.failure_count == 1
        assert quality.effectiveness == 0.5

        report = ChallengeReport(
            challenge_id="r13-lesson-demo",
            summary="A fake-local Web run produced a reviewed result.",
            domain="web",
            status="COMPLETED",
            key_findings=({
                "title": "Authentication state difference",
                "description": "Captured states differed.",
                "artifact_refs": [{"artifact_id": "artifact-r13-finding"}],
            },),
            experiments=(
                {
                    "experiment_id": "experiment-r13-success",
                    "goal": "compare bounded state behavior",
                    "status": "SUCCESS",
                },
                {
                    "experiment_id": "experiment-r13-failure",
                    "goal": "repeat an unsupported state comparison",
                    "status": "FAILED",
                },
            ),
            artifacts=(),
            evidence=(
                {
                    "evidence_id": "evidence-r13-success",
                    "experiment_id": "experiment-r13-success",
                    "artifact_refs": [{"artifact_id": "artifact-r13-success"}],
                },
                {
                    "evidence_id": "evidence-r13-failure",
                    "experiment_id": "experiment-r13-failure",
                    "artifact_refs": [{"artifact_id": "artifact-r13-failure"}],
                },
            ),
        )
        lessons = LessonExtractor().extract(report)
        assert {item.kind for item in lessons} == {
            LessonKind.SUCCESSFUL_STRATEGY,
            LessonKind.FAILED_STRATEGY,
            LessonKind.GENERAL_INSIGHT,
        }

    print("LOCAL_WEB_BENCHMARK_EXPERIENCE_EVOLUTION_OK")


if __name__ == "__main__":
    main()
