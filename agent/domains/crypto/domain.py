"""Crypto challenge knowledge classification only; no solver runtime."""

from agent.domains.base import RuleDomain


class CryptoDomain(RuleDomain):
    def __init__(self) -> None:
        super().__init__(
            name="crypto",
            description="Reasoning patterns for CTF cryptography and encoding challenges.",
            skill_names=("encoding", "classical_crypto", "hash_analysis"),
            signals=(
                "crypto", "cipher", "encrypt", "decrypt", "rsa", "aes", "base64",
                "hex", "hash", "md5", "sha1", "sha256", "caesar", "vigenere",
            ),
            skill_signals={
                "encoding": ("encoding", "base64", "hex", "base32", "ascii"),
                "classical_crypto": ("caesar", "vigenere", "substitution", "transposition"),
                "hash_analysis": ("hash", "md5", "sha1", "sha256", "digest"),
            },
        )
