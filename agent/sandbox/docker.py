"""Docker CLI backend for R9.2 sandbox container lifecycle operations."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Sequence, Tuple

from agent.sandbox.models import (
    DockerAvailability,
    SandboxExecutionError,
    SandboxResult,
    SandboxSpec,
    SandboxUnavailableError,
)


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
_CONTAINER_ID = re.compile(r"^[a-f0-9]{12,64}$")


class DockerBackend:
    """Perform explicit create, attach, timeout, and cleanup operations.

    The backend never uses a shell, never pulls an image, and never accepts
    caller-supplied Docker flags. SandboxManager is its only production caller.
    """

    def __init__(
        self,
        *,
        executable: str | None = None,
        runner: CommandRunner = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        user_id: int | None = None,
        group_id: int | None = None,
    ) -> None:
        self.executable = executable or which("docker")
        self._runner = runner
        detected_user = os.getuid() if hasattr(os, "getuid") else 65534
        detected_group = os.getgid() if hasattr(os, "getgid") else 65534
        self.user_id = user_id if user_id is not None else detected_user
        self.group_id = group_id if group_id is not None else detected_group
        if self.user_id == 0:
            self.user_id = 65534
        if self.group_id == 0:
            self.group_id = 65534

    def check(self) -> DockerAvailability:
        if self.executable is None:
            return DockerAvailability(
                client_available=False,
                daemon_available=False,
                error="Docker CLI was not found",
            )
        try:
            client = self._run([self.executable, "--version"], timeout=5)
        except (OSError, subprocess.SubprocessError) as error:
            return DockerAvailability(False, False, error=str(error))
        if client.returncode != 0:
            return DockerAvailability(
                False,
                False,
                error=(client.stderr or client.stdout or "Docker CLI check failed").strip(),
            )
        version = (client.stdout or "").strip()
        environment_endpoint = os.environ.get("DOCKER_HOST", "").strip()
        if environment_endpoint and not environment_endpoint.startswith(
            ("unix://", "npipe://")
        ):
            return DockerAvailability(
                True,
                False,
                version=version,
                error="remote Docker endpoints from DOCKER_HOST are forbidden",
            )
        try:
            current_context = self._run(
                [self.executable, "context", "show"],
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return DockerAvailability(True, False, version=version, error=str(error))
        context_name = (current_context.stdout or "").strip()
        if current_context.returncode != 0 or not context_name:
            return DockerAvailability(
                True,
                False,
                version=version,
                error=(
                    current_context.stderr
                    or current_context.stdout
                    or "Docker context check failed"
                ).strip(),
            )
        try:
            context = self._run(
                [
                    self.executable,
                    "context",
                    "inspect",
                    context_name,
                    "--format",
                    '{{(index .Endpoints "docker").Host}}',
                ],
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return DockerAvailability(True, False, version=version, error=str(error))
        endpoint = (context.stdout or "").strip()
        if (
            context.returncode != 0
            or not endpoint.startswith(("unix://", "npipe://"))
        ):
            return DockerAvailability(
                True,
                False,
                version=version,
                error="remote or unresolved Docker contexts are forbidden",
            )
        try:
            daemon = self._run(
                [self.executable, "info", "--format", "{{.ServerVersion}}"],
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return DockerAvailability(True, False, version=version, error=str(error))
        if daemon.returncode != 0:
            return DockerAvailability(
                True,
                False,
                version=version,
                error=(daemon.stderr or daemon.stdout or "Docker daemon check failed").strip(),
            )
        server_version = (daemon.stdout or "").strip()
        combined_version = version
        if server_version:
            combined_version = f"{version}; server {server_version}"
        return DockerAvailability(True, True, version=combined_version)

    def image_available(self, image: str) -> bool:
        """Check local image presence without invoking an implicit pull."""

        if self.executable is None:
            return False
        try:
            result = self._run(
                [self.executable, "image", "inspect", image],
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def create(self, spec: SandboxSpec, command: Sequence[str]) -> str:
        availability = self.check()
        if not availability.available:
            raise SandboxUnavailableError(
                availability.error or "Docker daemon is unavailable"
            )
        if not self.image_available(spec.image):
            raise SandboxUnavailableError(
                f"sandbox image is not available locally: {spec.image}"
            )
        create_command = self._create_command(spec, command)
        try:
            result = self._run(create_command, timeout=15)
        except (OSError, subprocess.SubprocessError) as error:
            raise SandboxExecutionError(f"Docker container create failed: {error}") from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown Docker error").strip()
            raise SandboxExecutionError(f"Docker container create failed: {detail}")
        container_id = (result.stdout or "").strip()
        if not _CONTAINER_ID.fullmatch(container_id):
            raise SandboxExecutionError("Docker returned an invalid container identifier")
        return container_id

    def run(
        self,
        container_id: str,
        spec: SandboxSpec,
    ) -> SandboxResult:
        self._validate_container_id(container_id)
        if self.executable is None:
            raise SandboxUnavailableError("Docker CLI was not found")
        started = time.monotonic()
        try:
            process = self._run(
                [self.executable, "start", "--attach", container_id],
                timeout=float(spec.timeout),
            )
        except subprocess.TimeoutExpired as error:
            return SandboxResult(
                success=False,
                stdout=self._timeout_stream(error.stdout),
                stderr=self._timeout_stream(error.stderr),
                exit_code=124,
                duration=max(0.0, time.monotonic() - started),
                timed_out=True,
                container_id=container_id,
                spec=spec,
                error=f"sandbox execution exceeded {float(spec.timeout):g} seconds",
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise SandboxExecutionError(f"Docker container run failed: {error}") from error
        return SandboxResult(
            success=process.returncode == 0,
            stdout=process.stdout or "",
            stderr=process.stderr or "",
            exit_code=process.returncode,
            duration=max(0.0, time.monotonic() - started),
            timed_out=False,
            container_id=container_id,
            spec=spec,
            error=None if process.returncode == 0 else "sandbox process exited unsuccessfully",
        )

    def cleanup(self, container_id: str) -> Tuple[bool, str]:
        self._validate_container_id(container_id)
        if self.executable is None:
            return False, "Docker CLI was not found during cleanup"
        try:
            result = self._run(
                [self.executable, "rm", "--force", container_id],
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return False, str(error)
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "container cleanup failed").strip()
        return True, ""

    def _create_command(
        self,
        spec: SandboxSpec,
        command: Sequence[str],
    ) -> list[str]:
        if self.executable is None:
            raise SandboxUnavailableError("Docker CLI was not found")
        if not command or any(not isinstance(item, str) or not item or "\x00" in item for item in command):
            raise SandboxExecutionError("sandbox command must contain non-empty arguments")
        result = [
            self.executable,
            "create",
            "--network",
            "none",
            "--cpus",
            f"{float(spec.cpu_limit):g}",
            "--memory",
            spec.memory_limit,
            "--pids-limit",
            "64",
            "--ulimit",
            "nofile=256:256",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            f"{self.user_id}:{self.group_id}",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--workdir",
            "/workspace/work",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONUNBUFFERED=1",
            "--label",
            "agonionce.sandbox=r9.2",
        ]
        for mount in spec.mounts:
            mount_value = (
                f"type=bind,src={Path(mount.source).resolve()},dst={mount.target}"
            )
            if mount.read_only:
                mount_value += ",readonly"
            result.extend(["--mount", mount_value])
        result.extend([spec.image, *command])
        return result

    def _run(
        self,
        command: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        return self._runner(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    @staticmethod
    def _validate_container_id(container_id: str) -> None:
        if not _CONTAINER_ID.fullmatch(container_id):
            raise SandboxExecutionError("invalid Docker container identifier")

    @staticmethod
    def _timeout_stream(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value
