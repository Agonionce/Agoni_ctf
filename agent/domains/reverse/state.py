"""Reverse runtime metadata interface."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReverseRuntimeMetadata:
    artifact_type: str | None = None
    architecture: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
