"""Evidence-bound writeup draft generation for the private R8.6 run record."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from agent.challenge.models import ChallengeManifest
from agent.completion.models import ChallengeReport
from agent.completion.report import ReportGenerator


class WriteupGenerator:
    """Create a draft without inventing actions or evidence.

    A confirmed candidate is included as a local verification result, never as
    an automatic submission instruction.
    """

    def generate(
        self,
        manifest: ChallengeManifest,
        report: ChallengeReport,
        *,
        lessons: Iterable[str] | None = None,
    ) -> str:
        if manifest.challenge_id != report.challenge_id:
            raise ValueError("manifest and report belong to different challenges")
        lesson_items = list(lessons) if lessons is not None else ReportGenerator.derive_lessons(report)
        lines = [
            f"# {manifest.name}",
            "",
            "## Challenge Description",
            "",
            manifest.description,
            "",
            "## Recon",
            "",
        ]
        findings = list(report.key_findings)
        lines.extend(
            [
                f"- **{_inline(item.get('title', 'Finding'))}:** "
                f"{_inline(item.get('description', ''))}"
                for item in findings
            ]
            or ["_No evidence-backed recon findings were persisted._"]
        )
        lines.extend(["", "## Analysis", ""])
        lines.extend(self._analysis(report.evidence))
        lines.extend(["", "## Exploitation Process", ""])
        lines.extend(self._experiments(report.experiments))
        lines.extend(["", "## Evidence", ""])
        lines.extend(self._evidence(report.evidence))
        lines.extend(["", "## Analysis Materials", ""])
        lines.extend(self._artifacts(report.artifacts))
        lines.extend(
            [
                "",
                "## Solution",
                "",
                f"The persisted run ended with status `{report.status}`. "
                "No additional solution steps were inferred.",
                "",
                "## Flag",
                "",
                "Flag result: "
                f"`{report.flag_verification.get('status', 'NONE')}`.",
                "",
                "## Lessons Learned",
                "",
            ]
        )
        lesson_index = lines.index("## Lessons Learned")
        lines[lesson_index:lesson_index] = self._candidate_verification(report.flag_verification) + [""]
        lines.extend([f"- {_inline(item)}" for item in lesson_items] or ["_No lesson derived._"])
        return "\n".join(lines).rstrip() + "\n"

    def write(
        self,
        manifest: ChallengeManifest,
        report: ChallengeReport,
        path: str | Path,
        *,
        lessons: Iterable[str] | None = None,
    ) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            self.generate(manifest, report, lessons=lessons),
            encoding="utf-8",
        )
        return output

    @staticmethod
    def _analysis(items: Iterable[Mapping[str, object]]) -> list[str]:
        evidence = list(items)
        if not evidence:
            return ["_No evidence-backed analysis was persisted._"]
        return [
            "The draft records the observations below without promoting them "
            "to conclusions beyond the stored IntelligenceState."
        ]

    @staticmethod
    def _experiments(items: Iterable[Mapping[str, object]]) -> list[str]:
        lines = [
            f"- `{item.get('experiment_id', '-')}` — "
            f"{_inline(item.get('goal', ''))}; actual result: "
            f"{_inline(item.get('actual_result', 'Not recorded')) or 'Not recorded'}; "
            f"status: `{_inline(item.get('status', '-'))}`."
            for item in items
        ]
        return lines or ["_No evidence-backed experiment steps were persisted._"]

    @staticmethod
    def _evidence(items: Iterable[Mapping[str, object]]) -> list[str]:
        lines: list[str] = []
        for item in items:
            lines.append(
                f"- `{item.get('evidence_id', '-')}` "
                f"({_inline(item.get('source', '-'))}): "
                f"{_inline(item.get('observation', ''))}"
            )
            paths = item.get("artifact_paths", [])
            if isinstance(paths, list) and paths:
                lines.append(
                    "  - Evidence file paths: "
                    + ", ".join(f"`{_inline(value)}`" for value in paths)
                )
        return lines or ["_No evidence records were persisted._"]

    @staticmethod
    def _artifacts(items: Iterable[Mapping[str, object]]) -> list[str]:
        lines = [
            f"- `{_inline(item.get('path', ''))}`"
            + (
                f" ({_inline(item.get('artifact_type', 'analysis material'))})"
                if item.get("artifact_type")
                else ""
            )
            for item in items
            if item.get("path")
        ]
        return lines or ["_No analysis material paths were persisted._"]

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
