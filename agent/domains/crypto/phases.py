"""Declarative Crypto lifecycle phases; no solver implementation."""

from enum import Enum

from agent.domains.base.runtime import PhaseDefinition


class CryptoPhase(str, Enum):
    CLASSIFICATION = "CLASSIFICATION"
    ANALYSIS = "ANALYSIS"
    SOLVING = "SOLVING"
    VERIFY = "VERIFY"


CRYPTO_PHASES = (
    PhaseDefinition(
        CryptoPhase.CLASSIFICATION.value,
        "Classify the representation or cryptographic family from supplied evidence.",
        ("alphabet and length properties", "candidate family", "known constraints"),
        ("encoding", "classical_crypto", "hash_analysis"),
        (CryptoPhase.ANALYSIS.value,),
    ),
    PhaseDefinition(
        CryptoPhase.ANALYSIS.value,
        "Identify assumptions, invariants, and candidate-space constraints.",
        ("supported model", "candidate constraints", "rejected interpretations"),
        ("encoding", "classical_crypto", "hash_analysis"),
        (CryptoPhase.SOLVING.value,),
    ),
    PhaseDefinition(
        CryptoPhase.SOLVING.value,
        "Apply the selected reasoning strategy to the local challenge material.",
        ("candidate result", "transformation record", "failure evidence"),
        ("encoding", "classical_crypto", "hash_analysis"),
        (CryptoPhase.VERIFY.value,),
    ),
    PhaseDefinition(
        CryptoPhase.VERIFY.value,
        "Verify the candidate against all available challenge constraints.",
        ("reproduced result", "format and consistency checks"),
        ("encoding", "classical_crypto", "hash_analysis"),
    ),
)
