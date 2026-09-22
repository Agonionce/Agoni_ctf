"""R1 first-class Tool contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agent.workspace.path import PUBLIC_WORKSPACE_SCOPES, WorkspacePathResolver


class ToolRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class ToolError:
    """Structured error returned at the controlled Tool boundary."""

    code: str
    message: str
    field_path: str = "$"
    schema_path: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "field_path": self.field_path,
            "schema_path": self.schema_path,
        }


@dataclass(frozen=True)
class ToolMetadata:
    name: str
    description: str
    risk_level: ToolRiskLevel
    requires_network: bool
    writes_files: bool
    execution_type: str
    path_argument_names: Tuple[str, ...] = ()
    path_scope_rules: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    autonomous_allowed: bool = False
    provenance: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionContext:
    """Audit and filesystem context supplied by ToolRuntime, never by Planner."""

    run_id: str
    challenge_id: str
    step_id: int
    workspace_root: Path
    input_dir: Path
    work_dir: Path
    output_dir: Path
    logs_dir: Path
    objective: str
    reasoning_summary: str
    authorized_targets: Tuple[str, ...] = ()
    execution_mode: str = "manual"

    def workspace_path_resolver(self) -> WorkspacePathResolver:
        return WorkspacePathResolver(
            self.workspace_root,
            scope_roots={
                "input": self.input_dir,
                "work": self.work_dir,
                "output": self.output_dir,
                "logs": self.logs_dir,
            },
        )

    def resolve_workspace_path(self, value: str | Path, base: Path | None = None) -> Path:
        resolver = self.workspace_path_resolver()
        if base is None:
            return resolver.resolve(value).path
        resolved_base = Path(base).resolve()
        if resolved_base == self.workspace_root.resolve():
            return resolver.resolve(
                value,
                allowed_scopes=("input", "work", "output", "logs"),
            ).path
        for scope, scope_root in resolver.scope_roots.items():
            if resolved_base == scope_root:
                return resolver.resolve(
                    value,
                    allowed_scopes=(scope,),
                    default_scope=scope,
                ).path
        raise ValueError("path base is outside a declared workspace scope")

    def resolve_workspace_uri(
        self,
        value: str | Path,
        *,
        allowed_scopes: Tuple[str, ...] = PUBLIC_WORKSPACE_SCOPES,
        default_scope: str = "work",
    ) -> Path:
        return self.workspace_path_resolver().resolve(
            value,
            allowed_scopes=allowed_scopes,
            default_scope=default_scope,
        ).path


@dataclass
class ToolExecutionOutput:
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error: str | None = None
    artifact_paths: List[Path] = field(default_factory=list)
    artifact_type: str = "file"
    artifact_types: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """Tool backends receive typed arguments and a constrained execution context."""

    metadata: ToolMetadata
    input_schema: Dict[str, Any]

    @abstractmethod
    def execute(
        self,
        arguments: Dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        """Execute one action after ToolRuntime has applied policy."""

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "input_schema": self.input_schema,
            "metadata": {
                "risk_level": self.metadata.risk_level.value,
                "requires_network": self.metadata.requires_network,
                "writes_files": self.metadata.writes_files,
                "execution_type": self.metadata.execution_type,
                "autonomous_allowed": self.metadata.autonomous_allowed,
                "provenance": dict(self.metadata.provenance),
                "path_scopes": {
                    name: list(scopes)
                    for name, scopes in self.metadata.path_scope_rules
                },
            },
        }
