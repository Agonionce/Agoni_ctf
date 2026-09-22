"""Structure-only Pwn domain runtime."""

from typing import Any, Mapping

from agent.domains.base.runtime import DomainRuntime
from agent.domains.pwn.phases import PWN_PHASES
from agent.domains.pwn.state import PwnRuntimeMetadata
from agent.runtime.contracts import ChallengeSpec


class PwnRuntime(DomainRuntime):
    name = "pwn"
    phase_definitions = PWN_PHASES

    def initial_details(self, challenge: ChallengeSpec) -> dict[str, Any]:
        architecture = challenge.metadata.get("architecture")
        binary_metadata = challenge.metadata.get("binary_metadata", {})
        return PwnRuntimeMetadata(
            architecture=(str(architecture) if architecture is not None else None),
            binary_metadata=(
                dict(binary_metadata) if isinstance(binary_metadata, Mapping) else {}
            ),
        ).to_dict()
