"""Termination decisions and FlagCandidate confirmation."""

from __future__ import annotations

import re
import json
from typing import Callable, Optional

from agent.runtime.contracts import (
    FlagCandidate,
    RunBudget,
    RunState,
    RunStatus,
    TerminationDecision,
    TerminationReason,
)


_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key)[a-z0-9_-]*\s*(?:=|:)\s*[\"']?",
    re.IGNORECASE,
)


class TerminationController:
    """Own the final stop decision; Analyzer never directly terminates a Run."""

    def __init__(self, budget: RunBudget) -> None:
        self.budget = budget

    def evaluate(
        self,
        state: RunState,
        budget_decision: Optional[TerminationDecision] = None,
        flag_confirmer: Optional[Callable[[object], bool]] = None,
    ) -> TerminationDecision:
        if state.last_analysis is not None and state.last_analysis.flag_candidates:
            # A challenge has one final Flag. Analyzer output may contain
            # several hypotheses.  Only an atomic, evidence-observed FLAG may
            # enter the terminal path; prose such as a description of a value
            # remains a lead, even when the authorized UI confirms automatically.
            eligible = [
                item
                for item in state.last_analysis.flag_candidates
                if is_verifiable_flag_candidate(state, item)
            ]
            if eligible:
                candidate = max(eligible, key=lambda item: item.confidence)
                if flag_confirmer is not None and flag_confirmer(candidate):
                    return TerminationDecision(
                        RunStatus.SOLVED,
                        TerminationReason.FLAG_CONFIRMED,
                        "final flag confirmed from observed evidence",
                        flag_candidate=candidate,
                    )

        failure_decision = None
        if state.counters.consecutive_failures >= self.budget.max_consecutive_failures:
            failure_decision = TerminationDecision(
                RunStatus.BLOCKED,
                TerminationReason.CONSECUTIVE_FAILURES,
                "consecutive failure threshold reached",
            )
        if failure_decision is not None:
            return failure_decision
        if budget_decision is not None:
            return budget_decision
        return TerminationDecision(RunStatus.RUNNING, TerminationReason.NONE, "continue")


def is_verifiable_flag_candidate(state: RunState, candidate: FlagCandidate) -> bool:
    """Check the minimal evidence binding required for a final Flag.

    The check intentionally supports non-braced local Flag formats.  On an
    ordinary runtime run, the exact value must be visible in a captured
    ToolResult.  Checkpoint-only legacy records without step data remain
    readable, but are still rejected if they are prose or a credential value.
    """

    if candidate.rejection_reason() is not None:
        return False
    if not state.steps:
        return not _looks_like_credential_assignment(
            f"{candidate.source}\n{candidate.evidence}"
        )
    for step in reversed(state.steps):
        for result in step.tool_results:
            observed = observed_tool_result_text(result)
            if candidate.value not in observed:
                continue
            if not _looks_like_credential_assignment(observed, candidate.value):
                return True
    return False


def observed_tool_result_text(result: object) -> str:
    """Return the captured textual observation, including structured metadata."""

    stdout = str(getattr(result, "stdout", "") or "")
    stderr = str(getattr(result, "stderr", "") or "")
    error = str(getattr(result, "error", "") or "")
    metadata = getattr(result, "metadata", {})
    try:
        metadata_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        metadata_text = ""
    return "\n".join(item for item in (stdout, stderr, error, metadata_text) if item)


def _looks_like_credential_assignment(observed: str, value: str = "") -> bool:
    """Recognize direct password/token assignment without imposing Flag syntax."""

    lowered = observed.lower()
    if value:
        index = lowered.find(value.lower())
        if index >= 0:
            lowered = lowered[max(0, index - 160) : index + len(value) + 32]
    return bool(_CREDENTIAL_ASSIGNMENT.search(lowered))
