"""Controlled Python execution inside the independent R9.2 Sandbox Layer."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict

from agent.sandbox.manager import SandboxManager
from agent.sandbox.models import SandboxSpec
from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
    ToolRiskLevel,
)


class SandboxPythonTool(Tool):
    """Run one contained workspace script without exposing Docker to Planner."""

    metadata = ToolMetadata(
        name="sandbox_python",
        description="Run a workspace Python script in a network-disabled local Docker sandbox.",
        risk_level=ToolRiskLevel.MEDIUM,
        requires_network=False,
        writes_files=True,
        execution_type="docker_sandbox",
        path_argument_names=("script",),
        path_scope_rules=(("script", ("input", "work")),),
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {
            "script": {"type": "string", "minLength": 1, "maxLength": 2048},
            "args": {
                "type": "array",
                "items": {"type": "string", "maxLength": 1024},
                "maxItems": 32,
            },
            "timeout": {
                "type": "number",
                "minimum": 0.1,
                "maximum": 300,
            },
        },
        "required": ["script"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        manager: SandboxManager,
        *,
        image: str = "python:3.12-alpine",
        cpu_limit: float = 1.0,
        memory_limit: str = "256m",
        default_timeout: float = 30.0,
    ) -> None:
        self.manager = manager
        self.image = image
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.default_timeout = default_timeout

    def execute(
        self,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        resolver = context.workspace_path_resolver()
        resolved_script = resolver.resolve(
            str(arguments["script"]),
            allowed_scopes=("input", "work"),
        )
        script = resolved_script.path
        if script.suffix.lower() != ".py":
            return ToolExecutionOutput(False, error="sandbox_python requires a .py script")
        if not script.is_file():
            return ToolExecutionOutput(False, error=f"script not found: {resolved_script.uri}")
        raw_args = arguments.get("args", [])
        args = [str(value) for value in raw_args]
        timeout = float(arguments.get("timeout", self.default_timeout))
        spec = self.manager.build_spec(
            workspace_root=context.workspace_root,
            input_dir=context.input_dir,
            work_dir=context.work_dir,
            output_dir=context.output_dir,
            image=self.image,
            network="none",
            cpu_limit=self.cpu_limit,
            memory_limit=self.memory_limit,
            timeout=timeout,
        )
        container_script = self._container_path(
            resolved_script.scope,
            resolved_script.relative_path,
        )
        result = self.manager.execute(
            spec,
            ["python3", "-I", container_script, *args],
            workspace_root=context.workspace_root,
            input_dir=context.input_dir,
            work_dir=context.work_dir,
            output_dir=context.output_dir,
        )
        artifact_path = self._write_artifact(
            context,
            spec,
            result.success,
            result.stdout,
            result.stderr,
            result.exit_code,
            result.duration,
            result.error,
            result.public_metadata(),
        )
        return ToolExecutionOutput(
            success=result.success,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            error=result.error,
            artifact_paths=[artifact_path],
            artifact_type="sandbox_execution",
            metadata={
                "duration": result.duration,
                "sandbox": result.public_metadata(),
            },
        )

    @staticmethod
    def _container_path(scope: str, relative_path: str) -> str:
        if scope not in {"input", "work"} or relative_path in {"", "."}:
            raise ValueError("sandbox script must identify a file in input or work")
        return f"/workspace/{scope}/{relative_path}"

    @staticmethod
    def _write_artifact(
        context: ExecutionContext,
        spec: SandboxSpec,
        success: bool,
        stdout: str,
        stderr: str,
        exit_code: int | None,
        duration: float,
        error: str | None,
        sandbox_metadata: Dict[str, Any],
    ) -> Path:
        artifact_dir = context.output_dir / "sandbox"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / (
            f"step-{context.step_id:04d}-{uuid.uuid4().hex[:12]}.json"
        )
        payload = {
            "schema_version": "r9.2",
            "success": success,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration": duration,
            "error": error,
            "sandbox": sandbox_metadata,
            "limits": spec.public_metadata(),
        }
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return artifact_path
