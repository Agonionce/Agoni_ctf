"""Executor contracts and legacy BaseTool compatibility."""

from __future__ import annotations

import time
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Protocol

from agent.runtime.contracts import ActionProposal, ToolResult


class Executor(Protocol):
    """Interface consumed by AgentRuntime."""

    def execute(self, proposal: ActionProposal) -> List[ToolResult]:
        """Execute all actions in proposal order."""


class ToolExecutor:
    """Adapt existing BaseTool-like objects to the R0 ToolResult contract.

    This class intentionally does not add R1 policy or sandboxing. New runtime
    callers must inject it explicitly and use the R0 manual approval boundary.
    """

    def __init__(self, tools: Mapping[str, Any]) -> None:
        self.tools = dict(tools)

    def execute(self, proposal: ActionProposal) -> List[ToolResult]:
        results: List[ToolResult] = []
        for call in proposal.actions:
            started_at = datetime.now(timezone.utc)
            started_clock = time.monotonic()
            tool = self.tools.get(call.tool_name)
            if tool is None:
                finished_at = datetime.now(timezone.utc)
                results.append(
                    ToolResult(
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        success=False,
                        error=f"unknown tool: {call.tool_name}",
                        started_at=started_at,
                        finished_at=finished_at,
                        duration=max(0.0, time.monotonic() - started_clock),
                    )
                )
                continue
            try:
                raw_output = tool.execute(call.tool_name, call.arguments)
                finished_at = datetime.now(timezone.utc)
                success, exit_code, stdout, stderr = self._normalize_output(raw_output)
                results.append(
                    ToolResult(
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        success=success,
                        exit_code=exit_code,
                        stdout=stdout,
                        stderr=stderr,
                        started_at=started_at,
                        finished_at=finished_at,
                        duration=max(0.0, time.monotonic() - started_clock),
                    )
                )
            except Exception as error:  # tool boundary normalizes failures
                finished_at = datetime.now(timezone.utc)
                results.append(
                    ToolResult(
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        success=False,
                        error=str(error),
                        started_at=started_at,
                        finished_at=finished_at,
                        duration=max(0.0, time.monotonic() - started_clock),
                    )
                )
        return results

    @staticmethod
    def _normalize_output(raw_output: Any) -> tuple[bool, int | None, str, str]:
        """Understand the existing BashShell envelope without coupling Runtime to it."""

        text = str(raw_output or "")
        match = re.match(
            r"^\[exit_code\]\s+(-?\d+)\n\[stdout\]\n(.*?)\n\[stderr\]\n(.*)$",
            text,
            re.DOTALL,
        )
        if match is None:
            return True, None, text, ""
        exit_code = int(match.group(1))
        return exit_code == 0, exit_code, match.group(2), match.group(3)
