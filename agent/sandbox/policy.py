"""Fail-closed R9.2 sandbox policy independent from Tool PolicyEngine."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Tuple

from agent.sandbox.models import (
    ALLOWED_MOUNT_TARGETS,
    SandboxConfigurationError,
    SandboxMount,
    SandboxSpec,
)


class SandboxPolicy:
    """Validate that Docker receives only the three declared workspace mounts."""

    _MOUNT_ACCESS = {
        "/workspace/input": True,
        "/workspace/work": False,
        "/workspace/output": False,
    }

    def workspace_mounts(
        self,
        *,
        input_dir: str | Path,
        work_dir: str | Path,
        output_dir: str | Path,
    ) -> Tuple[SandboxMount, ...]:
        return (
            SandboxMount(Path(input_dir), "/workspace/input", True),
            SandboxMount(Path(work_dir), "/workspace/work", False),
            SandboxMount(Path(output_dir), "/workspace/output", False),
        )

    def validate(
        self,
        spec: SandboxSpec,
        *,
        workspace_root: str | Path,
        input_dir: str | Path,
        work_dir: str | Path,
        output_dir: str | Path,
    ) -> None:
        """Reject network access and any mount outside the active workspace."""

        if spec.network != "none":
            raise SandboxConfigurationError("host or bridged networking is forbidden")
        root = Path(workspace_root).resolve()
        expected_sources: Mapping[str, Path] = {
            "/workspace/input": Path(input_dir).resolve(),
            "/workspace/work": Path(work_dir).resolve(),
            "/workspace/output": Path(output_dir).resolve(),
        }
        canonical_sources: Mapping[str, Path] = {
            "/workspace/input": (root / "input").resolve(),
            "/workspace/work": (root / "work").resolve(),
            "/workspace/output": (root / "output").resolve(),
        }
        if expected_sources != canonical_sources:
            raise SandboxConfigurationError(
                "sandbox workspace directories do not match the workspace contract"
            )
        mounts_by_target = {mount.target: mount for mount in spec.mounts}
        if set(mounts_by_target) != ALLOWED_MOUNT_TARGETS:
            raise SandboxConfigurationError(
                "sandbox must mount exactly input, work, and output"
            )
        for target, expected_source in expected_sources.items():
            mount = mounts_by_target[target]
            source = mount.source.resolve()
            if source != expected_source or not source.is_dir():
                raise SandboxConfigurationError(
                    f"sandbox mount source does not match {target}"
                )
            if "," in str(source) or "\x00" in str(source):
                raise SandboxConfigurationError("sandbox mount path is not portable")
            if mount.read_only is not self._MOUNT_ACCESS[target]:
                access = "read-only" if self._MOUNT_ACCESS[target] else "read-write"
                raise SandboxConfigurationError(f"{target} must be mounted {access}")
            try:
                source.relative_to(root)
            except ValueError as error:
                raise SandboxConfigurationError(
                    "host filesystem mounts outside the workspace are forbidden"
                ) from error
            if source.name in {"docker.sock", "podman.sock"}:
                raise SandboxConfigurationError("container engine socket mounts are forbidden")
