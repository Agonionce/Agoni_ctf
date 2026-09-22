"""R12 fake-local Web knowledge, benchmark, and experience-review demo."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.completion.experience import (
    ExperienceCandidateCatalog,
    ExperienceCandidateExtractor,
    ExperienceCandidateStore,
)
from agent.completion.models import ChallengeReport, ExperienceReviewStatus
from agent.domains.web.benchmark import WebBenchmarkLoader, WebBenchmarkRunner
from agent.experience.store import ExperienceStore
from demos.r11_web_autonomous_research import run_demo as run_research_loop


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    loader = WebBenchmarkLoader(repository / "benchmarks" / "web")
    with TemporaryDirectory(prefix="agonionce-r12-") as temporary:
        research_root = Path(temporary) / "research-loop"
        research_root.mkdir()
        assert run_research_loop(research_root)
        result_root = Path(temporary) / "benchmark-results"
        results = [
            WebBenchmarkRunner(loader).run(case, result_root=result_root)
            for case in loader.list()
        ]
        assert len(results) >= 4
        assert all(item.passed for item in results)

        report = ChallengeReport(
            challenge_id="r12-local-demo",
            summary="A local Web run completed with structured evidence.",
            domain="web",
            status="COMPLETED",
            key_findings=({
                "title": "Business state response",
                "description": "The quantity parameter changed the captured response state.",
            },),
            experiments=({
                "experiment_id": "experiment-local",
                "goal": "compare parameter response behavior",
                "expected_result": "business state difference recorded",
                "actual_result": "business state difference recorded",
                "status": "SUCCESS",
            },),
            artifacts=(),
            evidence=({
                "source": "fake-local benchmark",
                "observation": "Parameter and business state response evidence were recorded.",
            },),
        )
        candidates = ExperienceCandidateExtractor().extract(report)
        assert candidates
        challenge_root = Path(temporary) / "challenges"
        candidate_store = ExperienceCandidateStore(
            challenge_root / report.challenge_id / "experience_candidates.json",
            challenge_id=report.challenge_id,
        )
        candidate_store.replace_all(candidates)
        global_path = Path(temporary) / "global" / "experience.json"
        catalog = ExperienceCandidateCatalog(challenge_root, global_path)
        approved = catalog.approve(candidates[0].id)
        assert approved.review_status is ExperienceReviewStatus.APPROVED
        assert ExperienceStore(global_path).list()

    print("LOCAL_WEB_CAPABILITY_EVOLUTION_OK")


if __name__ == "__main__":
    main()
