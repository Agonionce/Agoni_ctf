"""Pwn runtime metadata interface; it performs no binary inspection."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PwnRuntimeMetadata:
    architecture: str | None = None
    binary_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
