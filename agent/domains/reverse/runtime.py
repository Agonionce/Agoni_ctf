"""Structure-only Reverse domain runtime."""

from typing import Any

from agent.domains.base.runtime import DomainRuntime
from agent.domains.reverse.phases import REVERSE_PHASES
from agent.domains.reverse.state import ReverseRuntimeMetadata
from agent.runtime.contracts import ChallengeSpec


class ReverseRuntime(DomainRuntime):
    name = "reverse"
    phase_definitions = REVERSE_PHASES

    def initial_details(self, challenge: ChallengeSpec) -> dict[str, Any]:
        artifact_type = challenge.metadata.get("artifact_type")
        architecture = challenge.metadata.get("architecture")
        return ReverseRuntimeMetadata(
            artifact_type=str(artifact_type) if artifact_type is not None else None,
            architecture=str(architecture) if architecture is not None else None,
        ).to_dict()
