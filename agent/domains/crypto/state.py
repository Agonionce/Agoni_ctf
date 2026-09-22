"""Crypto runtime metadata interface."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CryptoRuntimeMetadata:
    declared_family: str | None = None
    encoding_hint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
