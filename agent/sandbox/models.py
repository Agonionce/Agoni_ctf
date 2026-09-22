"""Typed contracts for the isolated R9.2 Sandbox Layer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Tuple


ALLOWED_MOUNT_TARGETS = frozenset(
    {
        "/workspace/input",
        "/workspace/work",
        "/workspace/output",
    }
)
_MEMORY_PATTERN = re.compile(r"^(?P<amount>[1-9][0-9]*)(?P<unit>[mMgG])$")
_IMAGE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:-]{0,255}$")


class SandboxConfigurationError(ValueError):
    """Raised when a sandbox request violates a typed safety contract."""


class SandboxUnavailableError(RuntimeError):
    """Raised when Docker cannot provide the requested local sandbox."""


class SandboxExecutionError(RuntimeError):
    """Raised when a container lifecycle operation cannot be completed."""


@dataclass(frozen=True)
class SandboxMount:
    """One explicitly allowed workspace bind mount."""

    source: Path
    target: str
    read_only: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", Path(self.source))
        if self.target not in ALLOWED_MOUNT_TARGETS:
            raise SandboxConfigurationError(
                f"sandbox mount target is not allowed: {self.target}"
            )

    def public_metadata(self) -> Dict[str, Any]:
        """Return container-side metadata without exposing a host path."""

        return {
            "target": self.target,
            "read_only": self.read_only,
        }


@dataclass(frozen=True)
class SandboxSpec:
    """Resource and containment limits for one local Docker execution."""

    image: str = "python:3.12-alpine"
    network: str = "none"
    cpu_limit: float = 1.0
    memory_limit: str = "256m"
    timeout: float = 30.0
    mounts: Tuple[SandboxMount, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "mounts", tuple(self.mounts))
        if (
            not isinstance(self.image, str)
            or _IMAGE_PATTERN.fullmatch(self.image) is None
        ):
            raise SandboxConfigurationError("sandbox image must be a non-empty image reference")
        if self.network != "none":
            raise SandboxConfigurationError("R9.2 sandbox networking must be disabled")
        if (
            isinstance(self.cpu_limit, bool)
            or not isinstance(self.cpu_limit, (int, float))
            or not 0 < float(self.cpu_limit) <= 4
        ):
            raise SandboxConfigurationError("sandbox cpu_limit must be greater than 0 and at most 4")
        memory_match = _MEMORY_PATTERN.fullmatch(str(self.memory_limit))
        if memory_match is None:
            raise SandboxConfigurationError("sandbox memory_limit must use an m or g suffix")
        amount = int(memory_match.group("amount"))
        unit = memory_match.group("unit").lower()
        memory_mib = amount * 1024 if unit == "g" else amount
        if not 32 <= memory_mib <= 2048:
            raise SandboxConfigurationError(
                "sandbox memory_limit must be between 32m and 2g"
            )
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not 0.1 <= float(self.timeout) <= 300
        ):
            raise SandboxConfigurationError(
                "sandbox timeout must be between 0.1 and 300 seconds"
            )
        targets = [mount.target for mount in self.mounts]
        if len(targets) != len(set(targets)):
            raise SandboxConfigurationError("sandbox mount targets must be unique")

    def public_metadata(self) -> Dict[str, Any]:
        return {
            "image": self.image,
            "network": self.network,
            "cpu_limit": float(self.cpu_limit),
            "memory_limit": self.memory_limit,
            "timeout": float(self.timeout),
            "mounts": [mount.public_metadata() for mount in self.mounts],
        }


@dataclass(frozen=True)
class DockerAvailability:
    """Read-only status returned by Docker environment checks."""

    client_available: bool
    daemon_available: bool
    version: str = ""
    error: str = ""

    @property
    def available(self) -> bool:
        return self.client_available and self.daemon_available


@dataclass(frozen=True)
class SandboxResult:
    """Normalized result produced by SandboxManager."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int | None
    duration: float
    timed_out: bool
    container_id: str
    spec: SandboxSpec
    cleanup_succeeded: bool = True
    error: str | None = None

    def public_metadata(self) -> Dict[str, Any]:
        metadata = self.spec.public_metadata()
        metadata.update(
            {
                "container_id": self.container_id[:12],
                "duration": self.duration,
                "timed_out": self.timed_out,
                "cleanup_succeeded": self.cleanup_succeeded,
            }
        )
        return metadata
