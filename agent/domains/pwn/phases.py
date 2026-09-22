"""Declarative Pwn lifecycle phases; no binary tooling."""

from enum import Enum

from agent.domains.base.runtime import PhaseDefinition


class PwnPhase(str, Enum):
    TRIAGE = "TRIAGE"
    PROTECTION_ANALYSIS = "PROTECTION_ANALYSIS"
    VULNERABILITY_ANALYSIS = "VULNERABILITY_ANALYSIS"
    EXPLOITATION = "EXPLOITATION"
    VERIFY = "VERIFY"


PWN_PHASES = (
    PhaseDefinition(
        PwnPhase.TRIAGE.value,
        "Establish declared binary format, architecture, interfaces, and evidence gaps.",
        ("binary metadata", "architecture", "interaction model"),
        ("binary_triage",),
        (PwnPhase.PROTECTION_ANALYSIS.value,),
    ),
    PhaseDefinition(
        PwnPhase.PROTECTION_ANALYSIS.value,
        "Organize available protection evidence and its strategy constraints.",
        ("declared mitigations", "unknown protection properties"),
        ("binary_triage",),
        (PwnPhase.VULNERABILITY_ANALYSIS.value,),
    ),
    PhaseDefinition(
        PwnPhase.VULNERABILITY_ANALYSIS.value,
        "Rank evidence-backed memory safety hypotheses and prerequisites.",
        ("minimal trigger evidence", "primitive hypothesis", "constraint list"),
        ("memory_corruption", "stack_overflow"),
        (PwnPhase.EXPLOITATION.value,),
    ),
    PhaseDefinition(
        PwnPhase.EXPLOITATION.value,
        "Evaluate a supported exploitation path in the authorized environment.",
        ("prerequisite status", "bounded test result", "failure reason"),
        ("memory_corruption", "stack_overflow", "ret2libc"),
        (PwnPhase.VERIFY.value,),
    ),
    PhaseDefinition(
        PwnPhase.VERIFY.value,
        "Verify repeatability and challenge completion evidence.",
        ("repeatable result", "completion evidence"),
        ("binary_triage",),
    ),
)
