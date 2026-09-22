"""Safe execution settings with compatibility defaults for older configs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class ExecutionMode(str, Enum):
    """Execution authority profiles supported by the R9.1 boundary."""

    MANUAL = "manual"
    SUPERVISED = "supervised"
    AUTONOMOUS_LOCAL = "autonomous_local"


@dataclass(frozen=True)
class ExecutionSettings:
    """R9.1 execution settings; absent configuration remains manual and safe."""

    mode: str = "manual"
    workspace_root: str = "workspace"
    default_policy: str = "safe"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ExecutionSettings":
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise ValueError("execution configuration must be an object")
        mode = data.get("mode", "manual")
        workspace_root = data.get("workspace_root", "workspace")
        default_policy = data.get("default_policy", "safe")
        if not isinstance(mode, str) or mode not in {
            item.value for item in ExecutionMode
        }:
            raise ValueError(
                "execution.mode must be manual, supervised, or autonomous_local"
            )
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            raise ValueError("execution.workspace_root must be a non-empty string")
        if default_policy != "safe":
            raise ValueError("R1 supports the safe default policy only")
        return cls(
            mode=mode,
            workspace_root=workspace_root,
            default_policy=default_policy,
        )
