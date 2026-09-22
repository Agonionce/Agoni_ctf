"""Canonical, evidence-bound Flag result selection across challenge runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from agent.intelligence.checkpoint import run_state_from_dict
from agent.runtime.contracts import FlagCandidate, RunState
from agent.runtime.termination import (
    is_verifiable_flag_candidate,
    observed_tool_result_text,
)


@dataclass(frozen=True)
class ChallengeFlagResult:
    """One read-only answer projection for a challenge, not an execution result."""

    challenge_id: str
    status: str
    value: str | None = None
    source: str | None = None
    evidence: str | None = None
    evidence_paths: tuple[str, ...] = ()
    run_number: int | None = None
    run_id: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "challenge_id": self.challenge_id,
            "status": self.status,
            "value": self.value,
            "source": self.source,
            "evidence": self.evidence,
            "evidence_paths": list(self.evidence_paths),
            "run_number": self.run_number,
            "run_id": self.run_id,
            "reason": self.reason,
        }


class ChallengeFlagResultResolver:
    """Resolve the canonical Flag without letting a later weak run erase it."""

    def resolve(self, challenge_id: str, runs_dir: str | Path) -> ChallengeFlagResult:
        candidates: list[tuple[int, Path, RunState, FlagCandidate]] = []
        latest_state: RunState | None = None
        for number, run_root in self._run_directories(Path(runs_dir)):
            state = self._run_state(run_root)
            if state is None or state.challenge.challenge_id != challenge_id:
                continue
            latest_state = state
            candidate = (
                state.termination.flag_candidate
                if state.termination is not None
                else None
            )
            if candidate is None or not is_verifiable_flag_candidate(state, candidate):
                continue
            candidates.append((number, run_root, state, candidate))

        if not candidates:
            return ChallengeFlagResult(
                challenge_id=challenge_id,
                status="NOT_FOUND",
                reason=self._not_found_reason(latest_state),
            )

        values = {candidate.value for _, _, _, candidate in candidates}
        if len(values) > 1:
            paths = tuple(
                dict.fromkeys(
                    path
                    for _, root, state, candidate in candidates
                    for path in self._candidate_paths(root, state, candidate)
                )
            )
            return ChallengeFlagResult(
                challenge_id=challenge_id,
                status="CONFLICT",
                evidence_paths=paths,
                reason="多个运行给出了不同的、可验证候选值；尚未形成唯一 Flag。",
            )

        number, run_root, state, candidate = max(
            candidates,
            key=lambda item: (item[3].confidence, item[0]),
        )
        return ChallengeFlagResult(
            challenge_id=challenge_id,
            status="FOUND",
            value=candidate.value,
            source=candidate.source,
            evidence=candidate.evidence,
            evidence_paths=tuple(self._candidate_paths(run_root, state, candidate)),
            run_number=number,
            run_id=state.run_id,
        )

    @staticmethod
    def _run_directories(runs_dir: Path) -> list[tuple[int, Path]]:
        if not runs_dir.is_dir():
            return []
        entries: list[tuple[int, Path]] = []
        for item in runs_dir.glob("run-*"):
            if not item.is_dir() or not (item / "run.json").is_file():
                continue
            try:
                entries.append((int(item.name.rsplit("-", 1)[-1]), item))
            except ValueError:
                continue
        return sorted(entries)

    @staticmethod
    def _run_state(run_root: Path) -> RunState | None:
        try:
            raw = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
            return run_state_from_dict(raw)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _candidate_paths(
        self,
        run_root: Path,
        state: RunState,
        candidate: FlagCandidate,
    ) -> list[str]:
        paths_by_id = self._artifact_paths(run_root)
        matched_refs: list[str] = []
        for step in state.steps:
            for result in step.tool_results:
                observed = observed_tool_result_text(result)
                if candidate.value in observed:
                    matched_refs.extend(result.artifact_refs)
        matched_paths = [
            paths_by_id[artifact_id]
            for artifact_id in matched_refs
            if artifact_id in paths_by_id
        ]
        if matched_paths:
            return list(dict.fromkeys(matched_paths))
        return list(dict.fromkeys(paths_by_id.values()))

    @staticmethod
    def _artifact_paths(run_root: Path) -> dict[str, str]:
        try:
            raw = json.loads(
                (run_root / "artifacts" / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, list):
            return {}
        return {
            str(item["artifact_id"]): str(item["path"])
            for item in raw
            if isinstance(item, Mapping)
            and isinstance(item.get("artifact_id"), str)
            and isinstance(item.get("path"), str)
            and item["artifact_id"]
            and item["path"]
        }

    @staticmethod
    def _not_found_reason(state: RunState | None) -> str:
        if state is None:
            return "题目尚未开始分析。"
        return {
            "BLOCKED": "现有证据不足，未形成最终 Flag。",
            "FAILED": "本轮运行失败，未形成最终 Flag。",
            "BUDGET_EXHAUSTED": "本轮已达到分析上限，未形成最终 Flag。",
            "ABORTED": "本轮已停止，未形成最终 Flag。",
            "PAUSED": "本轮已暂停，未形成最终 Flag。",
        }.get(state.status.value, "本轮尚未形成最终 Flag。")
