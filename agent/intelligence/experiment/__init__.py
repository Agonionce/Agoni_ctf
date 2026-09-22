"""R6 experiment-loop contracts and state managers.

This package manages reasoning state only. It never executes Tools; experiment
actions must still travel through ToolRuntime, PolicyEngine, and
ApprovalManager.
"""

from agent.intelligence.experiment.models import (
    EvidenceRecord,
    Experiment,
    ExperimentStatus,
)
from agent.intelligence.models import Hypothesis, HypothesisStatus

__all__ = [
    "EvidenceCollector",
    "EvidenceRecord",
    "Experiment",
    "ExperimentContextBuilder",
    "ExperimentExecutor",
    "ExperimentManager",
    "ExperimentPlanner",
    "ExperimentStatus",
    "Hypothesis",
    "HypothesisManager",
    "HypothesisStatus",
]


def __getattr__(name: str):
    """Load manager/context services lazily to keep model imports acyclic."""

    if name == "ExperimentContextBuilder":
        from agent.intelligence.experiment.context import ExperimentContextBuilder

        return ExperimentContextBuilder
    if name in {
        "EvidenceCollector",
        "ExperimentExecutor",
        "ExperimentManager",
        "ExperimentPlanner",
        "HypothesisManager",
    }:
        from agent.intelligence.experiment import manager

        return getattr(manager, name)
    raise AttributeError(name)
