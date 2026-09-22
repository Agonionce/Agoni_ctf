"""R13 aggregate reporting for persisted Web benchmark evaluations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from agent.domains.web.benchmark.models import WebBenchmarkEvaluationRecord


@dataclass(frozen=True)
class WebBenchmarkPerformanceReport:
    total_challenges: int
    total_runs: int
    solved_runs: int
    success_rate: float
    average_experiments: float
    average_evidence: float
    average_duration_seconds: float
    total_tool_calls: int
    experience_usage_runs: int
    experience_usage_count: int
    experience_usage_rate: float
    improvement_delta: float
    improvement_trend: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WebBenchmarkReportBuilder:
    def load(self, root: str | Path) -> list[WebBenchmarkEvaluationRecord]:
        result_root = Path(root)
        history = sorted((result_root / "history").glob("*/*.json"))
        paths = history or sorted(
            path for path in result_root.glob("*.json") if path.is_file()
        )
        records: list[WebBenchmarkEvaluationRecord] = []
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, Mapping):
                continue
            evaluation = raw.get("evaluation", raw)
            if not isinstance(evaluation, Mapping) or "evaluation_id" not in evaluation:
                continue
            records.append(WebBenchmarkEvaluationRecord.from_dict(evaluation))
        return sorted(records, key=lambda item: (item.generated_at, item.evaluation_id))

    def build(
        self,
        records: list[WebBenchmarkEvaluationRecord],
    ) -> WebBenchmarkPerformanceReport:
        total = len(records)
        solved = sum(item.solved for item in records)
        experience_runs = sum(bool(item.experience_usage) for item in records)
        if total >= 2:
            midpoint = total // 2
            earlier = records[:midpoint]
            recent = records[midpoint:]
            earlier_rate = sum(item.solved for item in earlier) / len(earlier)
            recent_rate = sum(item.solved for item in recent) / len(recent)
            delta = recent_rate - earlier_rate
            trend = "IMPROVING" if delta > 0 else "DECLINING" if delta < 0 else "STABLE"
        else:
            delta = 0.0
            trend = "INSUFFICIENT_DATA"
        denominator = total or 1
        return WebBenchmarkPerformanceReport(
            total_challenges=len({item.benchmark_id for item in records}),
            total_runs=total,
            solved_runs=solved,
            success_rate=solved / denominator if total else 0.0,
            average_experiments=(
                sum(len(item.experiments) for item in records) / denominator if total else 0.0
            ),
            average_evidence=(
                sum(len(item.evidence) for item in records) / denominator if total else 0.0
            ),
            average_duration_seconds=(
                sum(item.duration_seconds for item in records) / denominator if total else 0.0
            ),
            total_tool_calls=sum(sum(item.tool_usage.values()) for item in records),
            experience_usage_runs=experience_runs,
            experience_usage_count=sum(len(item.experience_usage) for item in records),
            experience_usage_rate=experience_runs / denominator if total else 0.0,
            improvement_delta=delta,
            improvement_trend=trend,
        )

    def from_directory(self, root: str | Path) -> WebBenchmarkPerformanceReport:
        return self.build(self.load(root))
