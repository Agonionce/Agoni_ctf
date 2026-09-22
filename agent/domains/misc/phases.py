"""Fallback lifecycle for challenges without a stronger domain classification."""

from enum import Enum

from agent.domains.base.runtime import PhaseDefinition


class MiscPhase(str, Enum):
    ORIENTATION = "ORIENTATION"
    ANALYSIS = "ANALYSIS"
    VERIFY = "VERIFY"


MISC_PHASES = (
    PhaseDefinition(
        MiscPhase.ORIENTATION.value,
        "Inventory supplied evidence and identify the next classification question.",
        ("artifact inventory", "candidate domains", "unknown formats"),
        ("misc_general",),
        (MiscPhase.ANALYSIS.value,),
    ),
    PhaseDefinition(
        MiscPhase.ANALYSIS.value,
        "Organize reversible observations and revise the domain hypothesis.",
        ("supported transformation", "domain evidence", "failed assumptions"),
        ("misc_general",),
        (MiscPhase.VERIFY.value,),
    ),
    PhaseDefinition(
        MiscPhase.VERIFY.value,
        "Verify the local result against challenge constraints.",
        ("repeatable result", "completion evidence"),
        ("misc_general",),
    ),
)
