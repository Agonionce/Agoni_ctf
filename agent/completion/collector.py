"""Read-only collection of a completed run into an R8.6 report model."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping

from agent.challenge.experience import ChallengeExperienceManager
from agent.challenge.models import ChallengeManifest
from agent.completion.models import ChallengeReport, utc_now_iso
from agent.intelligence.checkpoint import run_state_from_dict
from agent.intelligence.models import ArtifactReference, IntelligenceState
from agent.runtime.contracts import RunState, to_jsonable


_PRIVATE_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(?:flag|ctf)\{[^}\r\n]+\}"),
    re.compile(
        r"(?i)\b(?:password|passwd|token|cookie|secret|credential)"
        r"\s*[:=]\s*[^\s,;]+"
    ),
)
_PRIVATE_FIELD_PATTERN = re.compile(
    r"(?i)\b(?:password|passwd|token|cookie|secret|flag|credential)s?\b"
)
_INTERNAL_DISPLAY_PATTERN = re.compile(
    r"(?i)\b(?:planner(?:\s+reasoning)?|toolruntime|policyengine|"
    r"approvalmanager|agentruntime|[a-z][a-z0-9_]*tool)\b"
)


def sanitize_completion_text(value: object) -> str:
    """Redact secret values while preserving evidence wording and provenance."""

    text = str(value).strip()
    for pattern in _PRIVATE_VALUE_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    text = _INTERNAL_DISPLAY_PATTERN.sub("受控观察", text)
    return text


def display_completion_text(value: object) -> str:
    """Keep private challenge-run text intact for the local report projection."""

    return str(value).strip()


@dataclass(frozen=True)
class CompletionSnapshot:
    """Typed source state loaded for a completion command."""

    manifest: ChallengeManifest
    run_state: RunState
    intelligence_state: IntelligenceState
    artifacts: tuple[Dict[str, Any], ...]
    run_root: Path


@dataclass(frozen=True)
class CompletionOutputs:
    """Locations and typed values produced by one consolidation pass."""

    report: ChallengeReport
    candidates: tuple["ExperienceCandidate", ...]
    report_path: Path
    writeup_path: Path
    lessons_path: Path
    candidates_path: Path
    lesson_candidates_path: Path | None = None


class CompletionCollector:
    """Build a report without mutating runtime or intelligence state."""

    def __init__(self, *, clock: Callable[[], str] = utc_now_iso) -> None:
        self._clock = clock

    def collect(
        self,
        manifest: ChallengeManifest,
        run_state: RunState,
        intelligence_state: IntelligenceState,
        artifacts: Iterable[Any] = (),
    ) -> ChallengeReport:
        if run_state.challenge.challenge_id != manifest.challenge_id:
            raise ValueError("run state belongs to a different challenge")
        if intelligence_state.challenge_id != manifest.challenge_id:
            raise ValueError("intelligence belongs to a different challenge")

        key_findings = self._key_findings(intelligence_state)
        artifact_records = tuple(self._artifact_record(item) for item in artifacts)
        artifact_paths_by_id = {
            str(item["artifact_id"]): str(item["path"])
            for item in artifact_records
            if item.get("artifact_id") and item.get("path")
        }
        experiments = tuple(
            {
                "experiment_id": item.experiment_id,
                "hypothesis_id": item.hypothesis_id,
                "goal": display_completion_text(item.goal),
                "tool_name": display_completion_text(item.action.get("tool_name", "")),
                "expected_result": display_completion_text(item.expected_result),
                "actual_result": display_completion_text(item.actual_result),
                "status": item.status.value,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in intelligence_state.experiments
        )
        evidence = tuple(
            {
                "evidence_id": item.evidence_id,
                "experiment_id": item.experiment_id,
                "hypothesis_id": item.hypothesis_id,
                "source": display_completion_text(item.source),
                "observation": display_completion_text(item.observation),
                "artifact_refs": self._artifact_refs(item.artifact_refs, artifact_paths_by_id),
                "artifact_paths": [
                    artifact_paths_by_id[reference.artifact_id]
                    for reference in item.artifact_refs
                    if reference.artifact_id in artifact_paths_by_id
                ],
                "timestamp": item.timestamp,
            }
            for item in intelligence_state.evidence
        )
        status = run_state.status.value
        summary = (
            f"Run {run_state.run_id} finished with status {status}; "
            f"collected {len(key_findings)} findings, {len(experiments)} experiments, "
            f"{len(evidence)} evidence records, and {len(artifact_records)} artifacts."
        )
        candidate = (
            run_state.termination.flag_candidate
            if run_state.termination is not None
            else None
        )
        verified = candidate is not None
        detected = len(
            run_state.last_analysis.flag_candidates
            if run_state.last_analysis is not None else []
        )
        flag_verification = {
            "result": "FOUND" if verified else "NOT_FOUND",
            "status": (
                "VERIFIED" if verified else "EVIDENCE_BOUND" if detected else "NONE"
            ),
            "candidate_count": max(detected, 1 if verified else 0),
            # This is a private, challenge-local report for the authorized
            # operator.  It is never copied into the global Experience store.
            "value_persisted": verified,
            "candidate_value": candidate.value if candidate is not None else None,
            "candidate_source": candidate.source if candidate is not None else None,
            "candidate_evidence": candidate.evidence if candidate is not None else None,
            "candidate_artifact_paths": sorted(
                {
                    path
                    for evidence_item in evidence
                    for path in evidence_item.get("artifact_paths", [])
                    if path
                }
            ) if candidate is not None else [],
            "not_found_reason": (
                None
                if verified
                else {
                    "BLOCKED": "现有证据不足，未形成最终 Flag。",
                    "FAILED": "本轮运行失败，未形成最终 Flag。",
                    "BUDGET_EXHAUSTED": "本轮已达到分析上限，未形成最终 Flag。",
                    "ABORTED": "本轮被安全停止，未形成最终 Flag。",
                    "PAUSED": "本轮已暂停，未形成最终 Flag。",
                }.get(status, "本轮尚未形成最终 Flag。")
            ),
        }
        return ChallengeReport(
            challenge_id=manifest.challenge_id,
            summary=summary,
            domain=manifest.domain,
            status=status,
            key_findings=key_findings,
            experiments=experiments,
            artifacts=artifact_records,
            generated_at=self._clock(),
            evidence=evidence,
            flag_verification=flag_verification,
        )

    @staticmethod
    def load_latest(
        challenge_id: str,
        *,
        experience_root: str | Path = "experiences/challenges",
    ) -> CompletionSnapshot:
        """Load the latest fully bound run without consulting project config."""

        manager = ChallengeExperienceManager(experience_root)
        manifest = manager.store.get(challenge_id)
        if manifest is None:
            raise ValueError(f"unknown challenge ID: {challenge_id}")
        paths = manager.paths_for(manifest)
        candidates = [
            item
            for item in paths.runs_dir.glob("run-*")
            if item.is_dir() and (item / "run.json").is_file()
        ]
        if not candidates:
            raise ValueError(f"challenge has no completed run: {challenge_id}")
        run_root = max(
            candidates,
            key=lambda item: int(item.name.rsplit("-", 1)[-1]),
        )
        run_raw = _read_object(run_root / "run.json")
        intelligence_raw = _read_object(paths.intelligence_file)
        artifact_raw = _read_array(run_root / "artifacts" / "manifest.json")
        run_state = run_state_from_dict(run_raw)
        intelligence_state = IntelligenceState.from_dict(intelligence_raw)
        if run_state.challenge.challenge_id != manifest.challenge_id:
            raise ValueError("latest run belongs to a different challenge")
        if intelligence_state.challenge_id != manifest.challenge_id:
            raise ValueError("stored intelligence belongs to a different challenge")
        return CompletionSnapshot(
            manifest=manifest,
            run_state=run_state,
            intelligence_state=intelligence_state,
            artifacts=tuple(dict(item) for item in artifact_raw),
            run_root=run_root,
        )

    @classmethod
    def _key_findings(cls, state: IntelligenceState) -> tuple[Dict[str, Any], ...]:
        records: list[Dict[str, Any]] = []
        for item in state.facts:
            records.append(
                {
                    "kind": "fact",
                    "id": item.id,
                    "title": display_completion_text(item.category),
                    "description": display_completion_text(item.content),
                    "confidence": item.confidence.value,
                    "artifact_refs": cls._artifact_refs(item.artifact_refs),
                    "created_at": item.created_at,
                }
            )
        for item in state.findings:
            records.append(
                {
                    "kind": "finding",
                    "id": item.id,
                    "title": display_completion_text(item.title),
                    "description": display_completion_text(item.description),
                    "importance": item.importance.value,
                    "artifact_refs": cls._artifact_refs(item.related_artifacts),
                    "created_at": item.created_at,
                }
            )
        for item in state.endpoint_findings:
            parameters = list(item.parameters)
            description = (
                f"Parameters: {', '.join(parameters)}" if parameters else "No parameters recorded"
            )
            records.append(
                {
                    "kind": "endpoint",
                    "id": item.id,
                    "title": f"{item.method} {item.path}",
                    "description": description,
                    "confidence": item.confidence.value,
                    "artifact_refs": cls._artifact_refs(item.artifact_refs),
                    "created_at": item.created_at,
                }
            )
        return tuple(records)

    @staticmethod
    def _artifact_refs(
        references: Iterable[ArtifactReference],
        artifact_paths_by_id: Mapping[str, str] | None = None,
    ) -> list[Dict[str, str]]:
        paths = artifact_paths_by_id or {}
        return [
            {
                "artifact_id": reference.artifact_id,
                "relation_type": reference.relation_type,
                **(
                    {"path": paths[reference.artifact_id]}
                    if reference.artifact_id in paths
                    else {}
                ),
            }
            for reference in references
        ]

    @staticmethod
    def _artifact_record(value: Any) -> Dict[str, Any]:
        raw = to_jsonable(value)
        if not isinstance(raw, Mapping):
            return {"value": sanitize_completion_text(raw)}
        allowed = (
            "artifact_id",
            "path",
            "created_by",
            "created_at",
            "source_step",
            "artifact_type",
        )
        record = {key: raw[key] for key in allowed if key in raw}
        return record


class ChallengeCompletionPipeline:
    """Coordinate deterministic completion outputs outside AgentRuntime."""

    def __init__(self, collector: CompletionCollector | None = None) -> None:
        self.collector = collector or CompletionCollector()

    def complete(
        self,
        manifest: ChallengeManifest,
        run_state: RunState,
        intelligence_state: IntelligenceState,
        artifacts: Iterable[Any] = (),
        *,
        experience_root: str | Path = "experiences/challenges",
    ) -> CompletionOutputs:
        from agent.completion.experience import (
            ExperienceCandidateExtractor,
            ExperienceCandidateStore,
        )
        from agent.completion.report import ReportGenerator
        from agent.completion.lessons import LessonExtractor
        from agent.completion.writeup import WriteupGenerator

        report = self.collector.collect(
            manifest,
            run_state,
            intelligence_state,
            artifacts,
        )
        manager = ChallengeExperienceManager(experience_root)
        paths = manager.paths_for(manifest)
        if not paths.challenge_file.is_file():
            raise FileNotFoundError(paths.challenge_file)
        report_generator = ReportGenerator()
        lessons = report_generator.derive_lessons(report)
        lesson_candidates = LessonExtractor().extract(report)
        report_generator.write(
            report,
            paths.report_file,
            manifest=manifest,
            lessons=lessons,
        )
        WriteupGenerator().write(
            manifest,
            report,
            paths.writeup_file,
            lessons=lessons,
        )
        paths.lessons_file.write_text(
            f"# {manifest.name} Lessons\n\n"
            + ("\n".join(f"- {item}" for item in lessons) if lessons else "_No lesson derived._")
            + "\n",
            encoding="utf-8",
        )
        LessonExtractor.write(
            paths.lesson_candidates_file,
            manifest.challenge_id,
            lesson_candidates,
        )
        extracted = ExperienceCandidateExtractor().extract(
            report,
            report.experiments,
            lessons,
            lesson_candidates,
        )
        candidate_store = ExperienceCandidateStore(
            paths.experience_candidates_file,
            challenge_id=manifest.challenge_id,
        )
        candidates = candidate_store.merge_extracted(extracted)
        return CompletionOutputs(
            report=report,
            candidates=tuple(candidates),
            report_path=paths.report_file,
            writeup_path=paths.writeup_file,
            lessons_path=paths.lessons_file,
            candidates_path=paths.experience_candidates_file,
            lesson_candidates_path=paths.lesson_candidates_file,
        )

    def complete_latest(
        self,
        challenge_id: str,
        *,
        experience_root: str | Path = "experiences/challenges",
    ) -> CompletionOutputs:
        snapshot = CompletionCollector.load_latest(
            challenge_id,
            experience_root=experience_root,
        )
        return self.complete(
            snapshot.manifest,
            snapshot.run_state,
            snapshot.intelligence_state,
            snapshot.artifacts,
            experience_root=experience_root,
        )


def _read_object(path: Path) -> Dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path.name} must contain a JSON object")
    return dict(raw)


def _read_array(path: Path) -> list[Dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not all(isinstance(item, Mapping) for item in raw):
        raise ValueError(f"{path.name} must contain an array of objects")
    return [dict(item) for item in raw]
