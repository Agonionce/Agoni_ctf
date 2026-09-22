"""The minimal R1 built-in Tool set: file, python and bash."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
    ToolRiskLevel,
)


class FileInfoTool(Tool):
    metadata = ToolMetadata(
        name="file",
        description="Inspect metadata for one file inside the challenge workspace.",
        risk_level=ToolRiskLevel.LOW,
        requires_network=False,
        writes_files=False,
        execution_type="python",
        path_argument_names=("path",),
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(
        self,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        path = context.resolve_workspace_uri(str(arguments["path"]))
        if not path.exists():
            return ToolExecutionOutput(False, error=f"file not found: {path}")
        stat = path.stat()
        payload = {
            "path": str(path.relative_to(context.workspace_root)),
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
            "size": stat.st_size,
            "suffix": path.suffix,
        }
        return ToolExecutionOutput(True, stdout=json.dumps(payload, ensure_ascii=False))


class PythonExecutionTool(Tool):
    metadata = ToolMetadata(
        name="python",
        description="Run a Python script located inside the challenge workspace.",
        risk_level=ToolRiskLevel.MEDIUM,
        requires_network=False,
        writes_files=True,
        execution_type="subprocess",
        path_argument_names=("script",),
    )
    input_schema = {
        "type": "object",
        "properties": {
            "script": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["script"],
        "additionalProperties": False,
    }

    def execute(
        self,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        script = context.resolve_workspace_path(str(arguments["script"]))
        if script.suffix != ".py":
            return ToolExecutionOutput(False, error="python tool requires a .py script")
        if not script.is_file():
            return ToolExecutionOutput(False, error=f"script not found: {script}")
        raw_args = arguments.get("args", [])
        if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
            return ToolExecutionOutput(False, error="args must be a list of strings")
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(script), *raw_args],
            cwd=context.work_dir,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONNOUSERSITE": "1"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        return ToolExecutionOutput(
            success=result.returncode == 0,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.returncode,
            metadata={"duration": max(0.0, time.monotonic() - started)},
        )


class BashTool(Tool):
    """R1 compatibility shell backend; ToolRuntime policy must authorize it."""

    metadata = ToolMetadata(
        name="bash",
        description="Run one policy-reviewed Bash command in the challenge workspace.",
        risk_level=ToolRiskLevel.MEDIUM,
        requires_network=False,
        writes_files=True,
        execution_type="subprocess",
    )
    input_schema = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
        "additionalProperties": False,
    }

    def execute(
        self,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return ToolExecutionOutput(False, error="command must be a non-empty string")
        started = time.monotonic()
        result = subprocess.run(
            ["bash", "-c", command],
            cwd=context.work_dir,
            env={"PATH": os.environ.get("PATH", ""), "HOME": str(context.work_dir)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        return ToolExecutionOutput(
            success=result.returncode == 0,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.returncode,
            metadata={"duration": max(0.0, time.monotonic() - started)},
        )
