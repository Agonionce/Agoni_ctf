"""Deterministic runner for captured fake-local Web benchmark evidence."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from agent.domains.web.artifacts import RequestArtifact, ResponseArtifact
from agent.domains.web.benchmark.loader import WebBenchmarkLoader
from agent.domains.web.benchmark.models import (
    WebBenchmarkCase,
    WebBenchmarkCheck,
    WebBenchmarkResult,
    WebBenchmarkEvaluationRecord,
    WebBenchmarkRunSnapshot,
)
from agent.domains.web.intelligence.manager import WebIntelligenceManager
from agent.domains.web.research.knowledge import WebKnowledgeModelEnhancer
from agent.domains.web.research.models import WebApplicationModel
from agent.experience.quality import (
    ExperienceFeedbackManager,
    ExperienceFeedbackOutcome,
    ExperienceQualityStore,
)
from agent.experience.store import ExperienceStore


class WebBenchmarkRunner:
    """Evaluate static captures; this class has no socket or Tool capability."""

    def __init__(self, loader: WebBenchmarkLoader | None = None) -> None:
        self.loader = loader or WebBenchmarkLoader()

    def run(
        self,
        case: WebBenchmarkCase,
        *,
        result_root: str | Path | None = None,
        run_snapshot: WebBenchmarkRunSnapshot | None = None,
        experience_store: ExperienceStore | None = None,
        quality_store: ExperienceQualityStore | None = None,
        apply_experience_feedback: bool = False,
        experience_usage: tuple[str, ...] = (),
    ) -> WebBenchmarkResult:
        started = time.monotonic()
        requests: list[RequestArtifact] = []
        responses: list[ResponseArtifact] = []
        for index, capture in enumerate(self.loader.captures(case), start=1):
            request_data = capture.get("request", {})
            response_data = capture.get("response", {})
            if not isinstance(request_data, Mapping) or not isinstance(response_data, Mapping):
                raise ValueError("each benchmark capture requires request and response objects")
            request_id = str(request_data.get("request_id") or f"{case.benchmark_id}-{index}")
            request = RequestArtifact.from_dict({
                "artifact_kind": "RequestArtifact",
                "request_id": request_id,
                "method": request_data.get("method", "GET"),
                "url": request_data.get("url", "http://localhost/"),
                "headers": request_data.get("headers", {}),
                "parameters": request_data.get("parameters", {}),
                "body": request_data.get("body"),
                "timeout": 1.0,
            })
            response = ResponseArtifact.from_dict({
                "artifact_kind": "ResponseArtifact",
                "request_id": request_id,
                "url": response_data.get("url", request.url),
                "status_code": response_data.get("status_code"),
                "reason": response_data.get("reason", ""),
                "headers": response_data.get("headers", []),
                "body": response_data.get("body", ""),
                "body_encoding": "utf-8",
                "truncated": False,
            })
            requests.append(request)
            responses.append(response)
        intelligence = WebIntelligenceManager().analyze(responses, requests=requests)
        model = WebApplicationModel()
        enhancer = WebKnowledgeModelEnhancer()
        request_by_id = {item.request_id: item for item in requests}
        for profile in intelligence.response_profiles:
            request = request_by_id.get(profile.request_id)
            enhancer.ingest_profile(
                model,
                profile,
                artifact_refs=[f"benchmark:{case.benchmark_id}:{profile.request_id}"],
                method=request.method if request is not None else "GET",
            )
        for difference in intelligence.state_differences:
            enhancer.ingest_difference(
                model,
                difference,
                artifact_refs=[f"benchmark:{case.benchmark_id}:comparison"],
            )
        for difference in intelligence.response_differences:
            if (
                difference.status_changed
                or difference.content_changed
                or difference.title_changed
                or difference.length_difference != 0
            ):
                from agent.domains.web.research.models import WebApplicationBehavior

                model.record_application_behavior(WebApplicationBehavior.create(
                    category="response_difference",
                    endpoint="",
                    observation=(
                        f"Captured responses {difference.baseline_request_id} and "
                        f"{difference.current_request_id} differ."
                    ),
                    evidence_type="RESPONSE_BEHAVIOR",
                    artifact_refs=[f"benchmark:{case.benchmark_id}:comparison"],
                ))
        checks = tuple(self._check(expectation, model) for expectation in case.expected_behavior)
        checks_passed = bool(checks) and all(item.passed for item in checks)
        elapsed = time.monotonic() - started
        if run_snapshot is None:
            run_snapshot = WebBenchmarkRunSnapshot(
                run_id=f"static-{case.benchmark_id}",
                result="PASS" if checks_passed else "FAIL",
                solved=checks_passed,
                evidence=tuple({
                    "source": "benchmark_check",
                    "observation": item.observation,
                    "passed": item.passed,
                } for item in checks),
                experience_usage=experience_usage,
                duration_seconds=elapsed,
            )
        elif run_snapshot.duration_seconds == 0:
            run_snapshot = replace(run_snapshot, duration_seconds=elapsed)
        model_summary = {
            "endpoints": len(model.endpoints),
            "parameters": len(model.parameters),
            "transitions": len(model.state_transitions),
            "behaviors": len(model.application_behaviors),
            "response_profiles": len(model.response_profiles),
        }
        evaluation = WebBenchmarkEvaluationRecord.create(
            case,
            run_snapshot,
            checks,
            model_summary,
        )
        result = WebBenchmarkResult(
            benchmark_id=case.benchmark_id,
            status="PASS" if evaluation.solved else "FAIL",
            checks=checks,
            model_summary=model_summary,
            evaluation=evaluation,
        )
        if apply_experience_feedback:
            if experience_store is None or quality_store is None:
                raise ValueError("explicit experience feedback requires both experience stores")
            manager = ExperienceFeedbackManager(experience_store, quality_store)
            evidence_refs = tuple(
                str(item.get("evidence_id"))
                for item in evaluation.evidence
                if item.get("evidence_id")
            )
            for experience_id in evaluation.experience_usage:
                manager.record(
                    experience_id,
                    source_run=evaluation.run_id,
                    source_challenge=case.benchmark_id,
                    outcome=(
                        ExperienceFeedbackOutcome.SUCCESS
                        if evaluation.solved
                        else ExperienceFeedbackOutcome.FAILURE
                    ),
                    solved=evaluation.solved,
                    evidence_refs=evidence_refs,
                )
        if result_root is not None:
            root = Path(result_root).resolve()
            output = root / f"{case.benchmark_id}.json"
            payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
            self._write_result(output, payload)
            history = root / "history" / case.benchmark_id / f"{evaluation.evaluation_id}.json"
            self._write_result(history, payload)
        return result

    @staticmethod
    def _write_result(path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _check(expectation: Mapping[str, Any], model: WebApplicationModel) -> WebBenchmarkCheck:
        kind = str(expectation.get("kind", ""))
        passed = False
        observation = "expectation not observed"
        if kind == "endpoint":
            path = str(expectation.get("path", ""))
            passed = any(item.path == path for item in model.endpoints)
            observation = f"endpoint {path} {'observed' if passed else 'missing'}"
        elif kind == "parameter":
            name = str(expectation.get("name", ""))
            role = str(expectation.get("semantic_role", ""))
            item = next((value for value in model.parameters if value.name == name), None)
            passed = item is not None and (not role or role in item.semantic_roles)
            observation = f"parameter {name}; roles={','.join(item.semantic_roles) if item else '-'}"
        elif kind == "authentication":
            endpoint = str(expectation.get("protected_endpoint", ""))
            status = str(expectation.get("status", ""))
            passed = (
                (not endpoint or endpoint in model.authentication.protected_endpoints)
                and (not status or model.authentication.status.value == status)
            )
            observation = (
                f"authentication={model.authentication.status.value}; "
                f"protected={','.join(model.authentication.protected_endpoints) or '-'}"
            )
        elif kind == "response":
            response_format = str(expectation.get("format", ""))
            error = str(expectation.get("error_pattern", ""))
            passed = any(
                (not response_format or item.response_format == response_format)
                and (not error or error in item.error_patterns)
                for item in model.response_profiles
            )
            observation = f"response format={response_format or '*'}; error={error or '*'}"
        elif kind == "state_transition":
            from_state = str(expectation.get("from_state", ""))
            to_state = str(expectation.get("to_state", ""))
            passed = any(
                (not from_state or item.from_state == from_state)
                and (not to_state or item.to_state == to_state)
                for item in model.state_transitions
            )
            observation = f"transition {from_state or '*'} -> {to_state or '*'}"
        elif kind == "application_behavior":
            category = str(expectation.get("category", ""))
            passed = any(item.category == category for item in model.application_behaviors)
            observation = f"application behavior {category} {'observed' if passed else 'missing'}"
        return WebBenchmarkCheck(dict(expectation), passed, observation)
