"""Structure-only fallback domain runtime."""

from typing import Any

from agent.domains.base.runtime import DomainRuntime
from agent.domains.misc.phases import MISC_PHASES
from agent.domains.misc.state import MiscRuntimeMetadata
from agent.runtime.contracts import ChallengeSpec


class MiscRuntime(DomainRuntime):
    name = "misc"
    phase_definitions = MISC_PHASES

    def initial_details(self, challenge: ChallengeSpec) -> dict[str, Any]:
        return MiscRuntimeMetadata(declared_category=challenge.category).to_dict()
