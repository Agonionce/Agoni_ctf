"""Safe fallback for challenges without a stronger domain signal."""

from agent.domains.base import RuleDomain


class MiscDomain(RuleDomain):
    def __init__(self) -> None:
        super().__init__(
            name="misc",
            description="General evidence-first reasoning for uncategorized CTF challenges.",
            skill_names=("misc_general",),
            signals=("misc", "general", "puzzle"),
            skill_signals={},
        )
