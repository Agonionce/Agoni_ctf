"""Structure-only Crypto domain runtime."""

from typing import Any

from agent.domains.base.runtime import DomainRuntime
from agent.domains.crypto.phases import CRYPTO_PHASES
from agent.domains.crypto.state import CryptoRuntimeMetadata
from agent.runtime.contracts import ChallengeSpec


class CryptoRuntime(DomainRuntime):
    name = "crypto"
    phase_definitions = CRYPTO_PHASES

    def initial_details(self, challenge: ChallengeSpec) -> dict[str, Any]:
        family = challenge.metadata.get("crypto_family")
        encoding = challenge.metadata.get("encoding_hint")
        return CryptoRuntimeMetadata(
            declared_family=str(family) if family is not None else None,
            encoding_hint=str(encoding) if encoding is not None else None,
        ).to_dict()
