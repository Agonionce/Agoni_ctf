"""Lifecycle coordinator for R9.2 sandbox execution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol, Sequence, Tuple

from agent.sandbox.docker import DockerBackend
from agent.sandbox.models import DockerAvailability, SandboxResult, SandboxSpec
from agent.sandbox.policy import SandboxPolicy


class SandboxBackend(Protocol):
    """Lifecycle contract implemented by Docker and deterministic test fakes."""

    def check(self) -> DockerAvailability:
        ...

    def image_available(self, image: str) -> bool:
        ...

    def create(self, spec: SandboxSpec, command: Sequence[str]) -> str:
        ...

    def run(self, container_id: str, spec: SandboxSpec) -> SandboxResult:
        ...

    def cleanup(self, container_id: str) -> Tuple[bool, str]:
        ...


class SandboxManager:
    """The only Sandbox Layer facade exposed to controlled Tools."""

    def __init__(
        self,
        backend: SandboxBackend | None = None,
        policy: SandboxPolicy | None = None,
    ) -> None:
        self.backend = backend or DockerBackend()
        self.policy = policy or SandboxPolicy()

    def check(self) -> DockerAvailability:
        return self.backend.check()

    def image_available(self, image: str) -> bool:
        """Check local image presence without exposing backend lifecycle APIs."""

        return self.backend.image_available(image)

    def build_spec(
        self,
        *,
        workspace_root: str | Path,
        input_dir: str | Path,
        work_dir: str | Path,
        output_dir: str | Path,
        image: str = "python:3.12-alpine",
        network: str = "none",
        cpu_limit: float = 1.0,
        memory_limit: str = "256m",
        timeout: float = 30.0,
    ) -> SandboxSpec:
        spec = SandboxSpec(
            image=image,
            network=network,
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
            timeout=timeout,
            mounts=self.policy.workspace_mounts(
                input_dir=input_dir,
                work_dir=work_dir,
                output_dir=output_dir,
            ),
        )
        self.policy.validate(
            spec,
            workspace_root=workspace_root,
            input_dir=input_dir,
            work_dir=work_dir,
            output_dir=output_dir,
        )
        return spec

    def execute(
        self,
        spec: SandboxSpec,
        command: Sequence[str],
        *,
        workspace_root: str | Path,
        input_dir: str | Path,
        work_dir: str | Path,
        output_dir: str | Path,
    ) -> SandboxResult:
        self.policy.validate(
            spec,
            workspace_root=workspace_root,
            input_dir=input_dir,
            work_dir=work_dir,
            output_dir=output_dir,
        )
        container_id = self.backend.create(spec, command)
        result: SandboxResult | None = None
        cleanup_succeeded = False
        cleanup_error = "container cleanup was not attempted"
        try:
            result = self.backend.run(container_id, spec)
        finally:
            cleanup_succeeded, cleanup_error = self.backend.cleanup(container_id)
        if result is None:
            raise RuntimeError("sandbox backend returned no result")
        if cleanup_succeeded:
            return result
        stderr = result.stderr
        if stderr and not stderr.endswith("\n"):
            stderr += "\n"
        stderr += f"sandbox cleanup failed: {cleanup_error}"
        return replace(
            result,
            success=False,
            stderr=stderr,
            cleanup_succeeded=False,
            error="sandbox container cleanup failed",
        )
