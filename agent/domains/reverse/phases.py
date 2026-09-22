"""Declarative Reverse lifecycle phases; no analysis-tool integration."""

from enum import Enum

from agent.domains.base.runtime import PhaseDefinition


class ReversePhase(str, Enum):
    TRIAGE = "TRIAGE"
    STATIC_ANALYSIS = "STATIC_ANALYSIS"
    DYNAMIC_ANALYSIS = "DYNAMIC_ANALYSIS"
    ALGORITHM_RECOVERY = "ALGORITHM_RECOVERY"


REVERSE_PHASES = (
    PhaseDefinition(
        ReversePhase.TRIAGE.value,
        "Establish artifact format, architecture, and likely behavior boundaries.",
        ("artifact metadata", "declared architecture", "visible behavior clues"),
        ("binary_analysis",),
        (ReversePhase.STATIC_ANALYSIS.value,),
    ),
    PhaseDefinition(
        ReversePhase.STATIC_ANALYSIS.value,
        "Organize static control-flow and data-flow evidence into testable hypotheses.",
        ("candidate decision points", "data-flow relationships", "unresolved branches"),
        ("binary_analysis", "static_analysis"),
        (ReversePhase.DYNAMIC_ANALYSIS.value, ReversePhase.ALGORITHM_RECOVERY.value),
    ),
    PhaseDefinition(
        ReversePhase.DYNAMIC_ANALYSIS.value,
        "Validate selected static hypotheses with bounded local observations.",
        ("runtime state comparison", "confirmed or rejected hypothesis"),
        ("dynamic_analysis",),
        (ReversePhase.ALGORITHM_RECOVERY.value,),
    ),
    PhaseDefinition(
        ReversePhase.ALGORITHM_RECOVERY.value,
        "Express the recovered challenge logic with evidence and remaining uncertainty.",
        ("recovered transformation", "validation evidence", "open assumptions"),
        ("binary_analysis", "static_analysis", "dynamic_analysis"),
    ),
)
