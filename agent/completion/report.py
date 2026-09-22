"""Deterministic Markdown report generation for the private R8.6 run record."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from agent.challenge.models import ChallengeManifest
from agent.completion.models import ChallengeReport


class ReportGenerator:
    """Render only fields collected from persisted challenge state.

    Candidate values are intentionally visible in this challenge-local report
    so the authorized operator can verify them manually; Experience extraction
    remains a separate sanitized path.
    """

    def generate(
        self,
        report: ChallengeReport,
        *,
        manifest: ChallengeManifest | None = None,
        lessons: Iterable[str] | None = None,
    ) -> str:
        name = manifest.name if manifest is not None else report.challenge_id
        lesson_items = list(lessons) if lessons is not None else self.derive_lessons(report)
        lines = [
            "# Challenge Report",
            "",
            "## Overview",
            "",
            f"- Challenge: {_inline(name)}",
            f"- Challenge ID: `{report.challenge_id}`",
            f"- Status: `{report.status}`",
            f"- Generated: `{report.generated_at}`",
            "",
            report.summary,
            "",
            "## Domain",
            "",
            report.domain,
            "",
            "## Timeline",
            "",
        ]
        timeline = self._timeline(report)
        lines.extend(timeline or ["_No persisted experiment or evidence timeline._"])
        lines.extend(["", "## Key Findings", ""])
        lines.extend(self._findings(report.key_findings))
        lines.extend(["", "## Experiments", ""])
        lines.extend(self._experiments(report.experiments))
        lines.extend(["", "## Evidence", ""])
        lines.extend(self._evidence(report.evidence))
        lines.extend(["", "## Analysis Materials", ""])
        lines.extend(self._artifacts(report.artifacts))
        lines.extend(
            [
                "",
                "## Result",
                "",
                f"Persisted run status: `{report.status}`.",
                "",
                "Flag result: "
                f"`{report.flag_verification.get('status', 'NONE')}`.",
                "",
                "## Lessons",
                "",
            ]
        )
        lesson_index = lines.index("## Lessons")
        lines[lesson_index:lesson_index] = self._candidate_verification(report.flag_verification) + [""]
        lines.extend([f"- {_inline(item)}" for item in lesson_items] or ["_No lesson derived._"])
        return "\n".join(lines).rstrip() + "\n"

    def write(
        self,
        report: ChallengeReport,
        path: str | Path,
        *,
        manifest: ChallengeManifest | None = None,
        lessons: Iterable[str] | None = None,
    ) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            self.generate(report, manifest=manifest, lessons=lessons),
            encoding="utf-8",
        )
        return output

    @staticmethod
    def derive_lessons(report: ChallengeReport) -> list[str]:
        lessons: list[str] = []
        if report.evidence:
            lessons.append(
                "Retain observation provenance before promoting an explanation to a conclusion."
            )
        if any(item.get("status") == "FAILED" for item in report.experiments):
            lessons.append(
                "Record failed experiments so later decisions do not repeat unsupported approaches."
            )
        if any(item.get("status") == "SUCCESS" for item in report.experiments):
            lessons.append(
                "Compare expected and actual results before closing the tested hypothesis."
            )
        if report.domain == "web":
            signal = " ".join(
                str(item.get(key, ""))
                for collection in (report.key_findings, report.evidence, report.experiments)
                for item in collection
                for key in ("title", "description", "observation", "goal", "actual_result")
            ).lower()
            if "parameter" in signal and "response" in signal:
                lessons.append(
                    "Relate user-controlled input to a captured response baseline before interpreting behavior."
                )
            if any(word in signal for word in ("authentication", "authorization", "forbidden")):
                lessons.append(
                    "Keep authentication state and authorization behavior as separate evidence-backed questions."
                )
        return lessons

    @staticmethod
    def _timeline(report: ChallengeReport) -> list[str]:
        events: list[tuple[str, str]] = []
        for item in report.experiments:
            events.append(
                (
                    str(item.get("updated_at", "")),
                    f"Experiment `{item.get('experiment_id', '-')}`: "
                    f"{_inline(item.get('status', '-'))}",
                )
            )
        for item in report.evidence:
            events.append(
                (
                    str(item.get("timestamp", "")),
                    f"Evidence `{item.get('evidence_id', '-')}` recorded from "
                    f"{_inline(item.get('source', '-'))}",
                )
            )
        return [
            f"- `{timestamp or 'unknown'}` — {description}"
            for timestamp, description in sorted(events, key=lambda item: item[0])
        ]

    @staticmethod
    def _findings(items: Iterable[Mapping[str, object]]) -> list[str]:
        lines = [
            f"- **{_inline(item.get('title', 'Untitled'))}** "
            f"({_inline(item.get('kind', 'finding'))}): "
            f"{_inline(item.get('description', ''))}"
            for item in items
        ]
        return lines or ["_No evidence-backed findings recorded._"]

    @staticmethod
    def _experiments(items: Iterable[Mapping[str, object]]) -> list[str]:
        lines: list[str] = []
        for item in items:
            lines.extend(
                [
                    f"### {_inline(item.get('experiment_id', 'Experiment'))}",
                    "",
                    f"- Goal: {_inline(item.get('goal', ''))}",
                    f"- Expected: {_inline(item.get('expected_result', ''))}",
                    f"- Actual: {_inline(item.get('actual_result', '')) or 'Not recorded'}",
                    f"- Status: `{_inline(item.get('status', '-'))}`",
                    "",
                ]
            )
        return lines or ["_No experiments recorded._"]

    @staticmethod
    def _evidence(items: Iterable[Mapping[str, object]]) -> list[str]:
        lines: list[str] = []
        for item in items:
            refs = item.get("artifact_refs", [])
            ref_ids = [
                str(ref.get("artifact_id"))
                for ref in refs
                if isinstance(ref, Mapping) and ref.get("artifact_id")
            ] if isinstance(refs, list) else []
            lines.append(
                f"- `{item.get('evidence_id', '-')}` "
                f"({_inline(item.get('source', '-'))}): "
                f"{_inline(item.get('observation', ''))}"
                + (f" — artifacts: {', '.join(f'`{value}`' for value in ref_ids)}" if ref_ids else "")
            )
            paths = item.get("artifact_paths", [])
            if isinstance(paths, list) and paths:
                lines.append(
                    "  - Evidence file paths: "
                    + ", ".join(f"`{_inline(value)}`" for value in paths)
                )
        return lines or ["_No evidence records persisted._"]

    @staticmethod
    def _artifacts(items: Iterable[Mapping[str, object]]) -> list[str]:
        lines: list[str] = []
        for item in items:
            path = item.get("path")
            if path:
                lines.append(
                    f"- `{_inline(path)}`"
                    + (
                        f" ({_inline(item.get('artifact_type', 'analysis material'))})"
                        if item.get("artifact_type")
                        else ""
                    )
                )
        return lines or ["_No analysis material paths persisted._"]

    @staticmethod
    def _candidate_verification(values: Mapping[str, object]) -> list[str]:
        candidate = values.get("candidate_value")
        if not candidate:
            return [
                "- Final Flag: 未找到",
                f"- Reason: {_inline(values.get('not_found_reason', '本轮未形成最终 Flag。'))}",
            ]
        lines = [
            f"- Final Flag: `{_inline(candidate)}`",
            f"- Supporting evidence: {_inline(values.get('candidate_evidence', ''))}",
            f"- Evidence source: {_inline(values.get('candidate_source', ''))}",
        ]
        paths = values.get("candidate_artifact_paths", [])
        if isinstance(paths, list) and paths:
            lines.append("- Evidence and analysis file paths:")
            lines.extend(f"  - `{_inline(path)}`" for path in paths)
        return lines


def _inline(value: object) -> str:
    return " ".join(str(value).strip().splitlines())
