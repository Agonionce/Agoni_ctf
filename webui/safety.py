"""Small normalization helpers for the loopback workbench projections."""

from __future__ import annotations

from urllib.parse import unquote


def repeatedly_unquote(value: str, *, rounds: int = 3) -> str:
    """Decode bounded percent-encoding so encoded secrets cannot bypass checks."""

    decoded = value
    for _ in range(rounds):
        candidate = unquote(decoded)
        if candidate == decoded:
            break
        decoded = candidate
    return decoded
