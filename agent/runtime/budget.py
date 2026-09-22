"""RunBudget enforcement and runtime accounting."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence

from agent.runtime.contracts import (
    AnalysisOutcome,
    RunBudget,
    RunCounters,
    RunState,
    RunStatus,
    TerminationDecision,
    TerminationReason,
    ToolResult,
)
from agent.runtime.errors import BudgetExceeded


@dataclass
class BudgetTracker:
    """Tracks limits without counting time spent paused for user approval."""

    budget: RunBudget
    counters: RunCounters
    clock: Callable[[], float] = time.monotonic
    _started_at: Optional[float] = None
    _paused_at: Optional[float] = None
    _paused_total: float = 0.0

    def start(self) -> None:
        if self._started_at is None:
            self._started_at = self.clock()

    def pause(self) -> None:
        if self._started_at is not None and self._paused_at is None:
            self._paused_at = self.clock()

    def resume(self) -> None:
        if self._paused_at is not None:
            self._paused_total += self.clock() - self._paused_at
            self._paused_at = None

    @property
    def elapsed(self) -> float:
        if self._started_at is None:
            return 0.0
        now = self.clock()
        paused = self._paused_total
        if self._paused_at is not None:
            paused += now - self._paused_at
        return max(0.0, now - self._started_at - paused)

    def reserve_llm_call(self, kind: str) -> None:
        if self.counters.llm_calls >= self.budget.max_llm_calls:
            raise BudgetExceeded("max_llm_calls reached")
        self.counters.llm_calls += 1
        if kind == "planner":
            self.counters.planner_calls += 1
        elif kind == "analyzer":
            self.counters.analyzer_calls += 1

    def pre_step_decision(self, state: RunState) -> Optional[TerminationDecision]:
        if state.current_step >= self.budget.max_steps:
            return TerminationDecision(
                RunStatus.BUDGET_EXHAUSTED,
                TerminationReason.MAX_STEPS,
                f"max_steps={self.budget.max_steps} reached",
            )
        if self.elapsed >= self.budget.max_runtime:
            return TerminationDecision(
                RunStatus.BUDGET_EXHAUSTED,
                TerminationReason.MAX_RUNTIME,
                f"max_runtime={self.budget.max_runtime}s reached",
            )
        if self.counters.llm_calls >= self.budget.max_llm_calls:
            return TerminationDecision(
                RunStatus.BUDGET_EXHAUSTED,
                TerminationReason.MAX_LLM_CALLS,
                f"max_llm_calls={self.budget.max_llm_calls} reached",
            )
        return None

    def register_actions(self, state: RunState, proposal) -> Optional[TerminationDecision]:
        for action in proposal.actions:
            fingerprint = action.fingerprint()
            state.action_counts[fingerprint] = state.action_counts.get(fingerprint, 0) + 1
        self.counters.duplicate_actions = sum(
            max(count - 1, 0) for count in state.action_counts.values()
        )
        if self.counters.duplicate_actions >= self.budget.max_duplicate_actions:
            return TerminationDecision(
                RunStatus.BLOCKED,
                TerminationReason.DUPLICATE_ACTIONS,
                f"duplicate action threshold={self.budget.max_duplicate_actions} reached",
            )
        return None

    def register_response_fingerprints(
        self,
        state: RunState,
        results: Sequence[ToolResult],
    ) -> list[str]:
        """Mark repeated captured Web responses without changing tool authority.

        Different request syntax that produces the same response is useful
        negative evidence.  The marker becomes part of the ordinary
        observation/evidence path, allowing the Analyzer and experiment
        evaluator to converge instead of mistaking HTTP transport success for
        a meaningful result.
        """

        repeated_call_ids: list[str] = []
        for result in results:
            fingerprint = self._response_fingerprint(result)
            if fingerprint is None:
                continue
            previous = state.response_counts.get(fingerprint, 0)
            state.response_counts[fingerprint] = previous + 1
            if previous <= 0:
                continue
            result.metadata["response_repeat"] = {
                "fingerprint": fingerprint,
                "previous_observations": previous,
            }
            repeated_call_ids.append(result.call_id)
        state.counters.repeated_responses += len(repeated_call_ids)
        return repeated_call_ids

    @staticmethod
    def _response_fingerprint(result: ToolResult) -> str | None:
        web = result.metadata.get("web_observation")
        if not isinstance(web, Mapping):
            return None
        full_digest = web.get("response_body_sha256")
        complete = web.get("response_body_complete")
        if isinstance(full_digest, str) and full_digest and complete is True:
            body_identity = {"full_body_sha256": full_digest}
        else:
            # Checkpoints created before complete-body digests existed remain
            # readable.  New HTTP observations always use the stronger branch
            # above, so a shared page prefix can no longer collapse distinct
            # long responses into one negative result.
            body = web.get("response_body_preview")
            if not isinstance(body, str):
                return None
            body_identity = {"legacy_preview": body}
        payload = json.dumps(
            {
                "tool": result.tool_name,
                "status": web.get("status_code"),
                "body": body_identity,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record_outcome(self, outcome: AnalysisOutcome) -> None:
        if outcome in {AnalysisOutcome.NO_PROGRESS, AnalysisOutcome.ACTION_FAILED}:
            self.counters.consecutive_failures += 1
            self.counters.failure_count += 1
        else:
            self.counters.consecutive_failures = 0

    def failure_decision(self) -> Optional[TerminationDecision]:
        if self.counters.consecutive_failures >= self.budget.max_consecutive_failures:
            return TerminationDecision(
                RunStatus.BLOCKED,
                TerminationReason.CONSECUTIVE_FAILURES,
                "consecutive failure threshold reached",
            )
        return None
