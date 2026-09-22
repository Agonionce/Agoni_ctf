"""Typed, JSON-safe R12 fake-local Web benchmark models."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from agent.intelligence.models import utc_now_iso
from agent.domains.web.research.models import (
    redact_web_context_text,
    redact_web_context_value,
)


@dataclass(frozen=True)
class WebBenchmarkCase:
    benchmark_id: str
    name: str
    category: str
    description: str
    source_files: tuple[str, ...]
    capture_file: str
    environment: dict[str, Any]
    expected_behavior: tuple[dict[str, Any], ...]
    evaluation: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", self.benchmark_id) is None:
            raise ValueError("benchmark_id must be a normalized local identifier")
        if not self.name.strip() or not self.category.strip():
            raise ValueError("benchmark name and category are required")
        if self.environment.get("kind") != "fake-local":
            raise ValueError("Web benchmarks must declare kind=fake-local")
        if self.environment.get("network") != "disabled":
            raise ValueError("Web benchmarks must disable network access")
        if self.evaluation.get("solved_when") != "all_expectations_pass":
            raise ValueError("Web benchmarks must use all_expectations_pass evaluation")
        minimum = self.evaluation.get("minimum_evidence")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum <= 0:
            raise ValueError("Web benchmark minimum_evidence must be positive")
        for relative in (*self.source_files, self.capture_file):
            if not relative or relative.startswith(("/", "~")) or ".." in relative.split("/"):
                raise ValueError("benchmark paths must be contained relative paths")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_files"] = list(self.source_files)
        payload["expected_behavior"] = [dict(item) for item in self.expected_behavior]
        return payload


@dataclass(frozen=True)
class WebBenchmarkCheck:
    expectation: dict[str, Any]
    passed: bool
    observation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WebBenchmarkRunSnapshot:
    """Normalized output of one Agent research run or static local evaluation."""

    run_id: str
    result: str
    solved: bool
    experiments: tuple[dict[str, Any], ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    hypotheses: tuple[dict[str, Any], ...] = ()
    tool_usage: dict[str, int] = field(default_factory=dict)
    experience_usage: tuple[str, ...] = ()
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        if re.fullmatch(r"[A-Za-z0-9._:-]+", self.run_id) is None:
            raise ValueError("benchmark run_id must be an opaque identifier")
        if not self.result.strip():
            raise ValueError("benchmark run result is required")
        if self.duration_seconds < 0:
            raise ValueError("benchmark duration cannot be negative")
        if any(value < 0 for value in self.tool_usage.values()):
            raise ValueError("tool usage counts cannot be negative")
        if any(
            re.fullmatch(r"[A-Za-z0-9._:-]+", item) is None
            for item in self.experience_usage
        ):
            raise ValueError("experience usage must contain opaque identifiers")

    @classmethod
    def from_completion(
        cls,
        report: Any,
        *,
        run_id: str,
        hypotheses: tuple[Any, ...] = (),
        tool_events: tuple[Mapping[str, Any], ...] = (),
        experience_usage: tuple[str, ...] = (),
        duration_seconds: float = 0.0,
    ) -> "WebBenchmarkRunSnapshot":
        """Adapt persisted Completion/Intelligence/Audit data without mutation."""

        experiments = tuple(dict(item) for item in getattr(report, "experiments", ()))
        evidence = tuple(dict(item) for item in getattr(report, "evidence", ()))
        hypothesis_items: list[dict[str, Any]] = []
        for item in hypotheses:
            if isinstance(item, Mapping):
                hypothesis_items.append(dict(item))
            elif callable(getattr(item, "to_dict", None)):
                raw = item.to_dict()
                if isinstance(raw, Mapping):
                    hypothesis_items.append(dict(raw))
        usage: dict[str, int] = {}
        for experiment in experiments:
            name = str(experiment.get("tool_name", "")).strip()
            if name:
                usage[name] = usage.get(name, 0) + 1
        for event in tool_events:
            name = str(event.get("tool", event.get("tool_name", ""))).strip()
            if name:
                usage[name] = usage.get(name, 0) + 1
        verification = getattr(report, "flag_verification", {})
        verified = (
            isinstance(verification, Mapping)
            and verification.get("status") == "VERIFIED"
        )
        status = str(getattr(report, "status", "UNKNOWN"))
        return cls(
            run_id=run_id,
            result=status,
            solved=verified or status.upper() == "SOLVED",
            experiments=experiments,
            evidence=evidence,
            hypotheses=tuple(hypothesis_items),
            tool_usage=usage,
            experience_usage=experience_usage,
            duration_seconds=duration_seconds,
        )


@dataclass(frozen=True)
class WebBenchmarkEvaluationRecord:
    evaluation_id: str
    benchmark_id: str
    challenge_metadata: dict[str, Any]
    run_id: str
    run_result: str
    solved: bool
    experiments: tuple[dict[str, Any], ...]
    evidence: tuple[dict[str, Any], ...]
    hypotheses: tuple[dict[str, Any], ...]
    tool_usage: dict[str, int]
    duration_seconds: float
    experience_usage: tuple[str, ...]
    checks: tuple[WebBenchmarkCheck, ...]
    model_summary: dict[str, int]
    generated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        case: WebBenchmarkCase,
        snapshot: WebBenchmarkRunSnapshot,
        checks: tuple[WebBenchmarkCheck, ...],
        model_summary: dict[str, int],
    ) -> "WebBenchmarkEvaluationRecord":
        checks_passed = bool(checks) and all(item.passed for item in checks)
        minimum_evidence = int(case.evaluation.get("minimum_evidence", 1))
        safe_experiments = redact_web_context_value(list(snapshot.experiments))
        safe_evidence = redact_web_context_value(list(snapshot.evidence))
        safe_hypotheses = redact_web_context_value(list(snapshot.hypotheses))
        return cls(
            evaluation_id=f"evaluation-{uuid.uuid4().hex[:12]}",
            benchmark_id=case.benchmark_id,
            challenge_metadata={
                "name": case.name,
                "category": case.category,
                "description": case.description,
                "environment": dict(case.environment),
                "evaluation": dict(case.evaluation),
            },
            run_id=snapshot.run_id,
            run_result=redact_web_context_text(snapshot.result),
            solved=bool(
                snapshot.solved
                and checks_passed
                and len(snapshot.evidence) >= minimum_evidence
            ),
            experiments=tuple(
                dict(item) for item in safe_experiments
                if isinstance(item, Mapping)
            ) if isinstance(safe_experiments, list) else (),
            evidence=tuple(
                dict(item) for item in safe_evidence
                if isinstance(item, Mapping)
            ) if isinstance(safe_evidence, list) else (),
            hypotheses=tuple(
                dict(item) for item in safe_hypotheses
                if isinstance(item, Mapping)
            ) if isinstance(safe_hypotheses, list) else (),
            tool_usage={str(key): int(value) for key, value in snapshot.tool_usage.items()},
            duration_seconds=float(snapshot.duration_seconds),
            experience_usage=tuple(dict.fromkeys(snapshot.experience_usage)),
            checks=checks,
            model_summary=dict(model_summary),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "evaluation_id": self.evaluation_id,
            "benchmark_id": self.benchmark_id,
            "challenge_metadata": dict(self.challenge_metadata),
            "run_id": self.run_id,
            "run_result": self.run_result,
            "solved": self.solved,
            "experiments": [dict(item) for item in self.experiments],
            "evidence": [dict(item) for item in self.evidence],
            "hypotheses": [dict(item) for item in self.hypotheses],
            "tool_usage": dict(self.tool_usage),
            "duration_seconds": self.duration_seconds,
            "experience_usage": list(self.experience_usage),
            "checks": [item.to_dict() for item in self.checks],
            "model_summary": dict(self.model_summary),
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebBenchmarkEvaluationRecord":
        def objects(name: str) -> tuple[dict[str, Any], ...]:
            return tuple(dict(item) for item in mapping_list(data.get(name)))

        checks = tuple(
            WebBenchmarkCheck(
                expectation=dict(item.get("expectation", {})),
                passed=bool(item.get("passed", False)),
                observation=str(item.get("observation", "")),
            )
            for item in mapping_list(data.get("checks"))
        )
        tool_usage = data.get("tool_usage", {})
        metadata = data.get("challenge_metadata", {})
        raw_experience = data.get("experience_usage", [])
        return cls(
            evaluation_id=str(data["evaluation_id"]),
            benchmark_id=str(data["benchmark_id"]),
            challenge_metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
            run_id=str(data["run_id"]),
            run_result=str(data.get("run_result", "UNKNOWN")),
            solved=bool(data.get("solved", False)),
            experiments=objects("experiments"),
            evidence=objects("evidence"),
            hypotheses=objects("hypotheses"),
            tool_usage=(
                {str(key): int(value) for key, value in tool_usage.items()}
                if isinstance(tool_usage, Mapping)
                else {}
            ),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            experience_usage=(
                tuple(str(item) for item in raw_experience)
                if isinstance(raw_experience, list)
                else ()
            ),
            checks=checks,
            model_summary={
                str(key): int(value)
                for key, value in data.get("model_summary", {}).items()
            } if isinstance(data.get("model_summary"), Mapping) else {},
            generated_at=str(data.get("generated_at") or utc_now_iso()),
        )


@dataclass(frozen=True)
class WebBenchmarkResult:
    benchmark_id: str
    status: str
    checks: tuple[WebBenchmarkCheck, ...]
    model_summary: dict[str, int]
    evaluation: WebBenchmarkEvaluationRecord | None = None
    generated_at: str = field(default_factory=utc_now_iso)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "benchmark_id": self.benchmark_id,
            "status": self.status,
            "checks": [item.to_dict() for item in self.checks],
            "model_summary": dict(self.model_summary),
            "generated_at": self.generated_at,
            "evaluation": self.evaluation.to_dict() if self.evaluation is not None else None,
        }


def mapping_list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]
