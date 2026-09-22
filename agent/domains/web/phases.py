"""Declarative Web lifecycle phases; no HTTP behavior."""

from enum import Enum

from agent.domains.base.runtime import PhaseDefinition


class WebPhase(str, Enum):
    RECON = "RECON"
    ANALYSIS = "ANALYSIS"
    EXPLOITATION = "EXPLOITATION"
    VERIFY = "VERIFY"


WEB_PHASES = (
    PhaseDefinition(
        WebPhase.RECON.value,
        "Establish the authorized application surface and available evidence.",
        ("declared entry points", "identity or session boundaries", "input locations"),
        ("web_general", "authentication"),
        (WebPhase.ANALYSIS.value,),
    ),
    PhaseDefinition(
        WebPhase.ANALYSIS.value,
        "Turn observed data flows and trust boundaries into ranked hypotheses.",
        ("reproducible response differences", "validation behavior", "supported hypotheses"),
        ("web_general", "authentication", "sql_injection", "xss", "ssrf"),
        (WebPhase.EXPLOITATION.value,),
    ),
    PhaseDefinition(
        WebPhase.EXPLOITATION.value,
        "Evaluate an evidence-backed challenge hypothesis within policy boundaries.",
        ("bounded hypothesis result", "failure reason", "new artifact reference"),
        ("authentication", "sql_injection", "xss", "ssrf"),
        (WebPhase.VERIFY.value,),
    ),
    PhaseDefinition(
        WebPhase.VERIFY.value,
        "Verify the result and preserve evidence without expanding target scope.",
        ("repeatable result", "challenge completion evidence"),
        ("web_general",),
    ),
)
