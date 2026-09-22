"""Misc runtime metadata interface."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MiscRuntimeMetadata:
    declared_category: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
