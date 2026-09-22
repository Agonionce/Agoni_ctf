"""Adapters that connect R4 lifecycle state without changing AgentRuntime."""

from __future__ import annotations

from agent.domains.manager import DomainRuntimeManager
from agent.runtime.analyzer import Analyzer
from agent.runtime.contracts import AnalysisResult, Observation, RunState


class DomainRuntimeAnalyzer:
    """Delegate analysis, then route its bounded summary to the R4 manager."""

    def __init__(self, delegate: Analyzer, manager: DomainRuntimeManager) -> None:
        self.delegate = delegate
        self.manager = manager

    def analyze(self, observation: Observation, state: RunState) -> AnalysisResult:
        result = self.delegate.analyze(observation, state)
        self.manager.route_observation(
            {
                "summary": result.summary,
                "observation": observation,
                "analysis": result,
            },
            phase_complete=False,
        )
        return result
