"""Create and resolve the minimal R1 filesystem boundary."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List

from agent.workspace.path import WorkspacePathResolver


@dataclass(frozen=True)
class Workspace:
    """Directories isolated for one challenge execution."""

    challenge_id: str
    root: Path
    input_dir: Path
    work_dir: Path
    output_dir: Path
    logs_dir: Path


class WorkspaceManager:
    """Manage only directories rooted under the configured workspace root."""

    def __init__(self, workspace_root: str | Path = "workspace") -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def create(self, challenge_id: str) -> Workspace:
        safe_id = self._safe_challenge_id(challenge_id)
        root = (self.workspace_root / safe_id).resolve()
        self._assert_under_root(root)
        input_dir = root / "input"
        work_dir = root / "work"
        output_dir = root / "output"
        logs_dir = root / "logs"
        for directory in (input_dir, work_dir, output_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return Workspace(safe_id, root, input_dir, work_dir, output_dir, logs_dir)

    def resolve_path(
        self,
        workspace: Workspace,
        value: str | Path,
        *,
        base: Path | None = None,
    ) -> Path:
        """Resolve a candidate path and reject traversal outside this workspace."""

        resolver = WorkspacePathResolver(workspace.root)
        if base is None:
            return resolver.resolve(value).path
        resolved_base = Path(base).resolve()
        default_scope = "work"
        if resolved_base == workspace.root.resolve():
            raw = Path(value)
            if raw.is_absolute():
                return resolver.resolve(raw, allowed_scopes=("input", "work", "output", "logs")).path
            parts = raw.parts
            if not parts or parts[0] not in {"input", "work", "output", "logs"}:
                raise ValueError("workspace-root relative paths must declare a scope")
            return resolver.resolve(
                raw,
                allowed_scopes=("input", "work", "output", "logs"),
            ).path
        for scope, scope_root in resolver.scope_roots.items():
            if resolved_base == scope_root:
                default_scope = scope
                break
        else:
            self._assert_within_workspace(workspace, resolved_base)
            candidate = (resolved_base / Path(value)).resolve()
            self._assert_within_workspace(workspace, candidate)
            return candidate
        return resolver.resolve(
            value,
            allowed_scopes=(default_scope,),
            default_scope=default_scope,
        ).path

    def list_files(self, workspace: Workspace) -> List[Path]:
        self._assert_under_root(workspace.root)
        return sorted(path for path in workspace.root.rglob("*") if path.is_file())

    def cleanup(self, workspace: Workspace) -> None:
        """Remove one explicitly created challenge workspace, never the root itself."""

        self._assert_under_root(workspace.root)
        if workspace.root == self.workspace_root:
            raise ValueError("refusing to remove workspace root")
        if workspace.root.exists():
            shutil.rmtree(workspace.root)

    @staticmethod
    def _safe_challenge_id(challenge_id: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", challenge_id).strip(".-")
        if not normalized:
            raise ValueError("challenge_id cannot resolve to an empty workspace name")
        return normalized

    def _assert_under_root(self, path: Path) -> None:
        try:
            path.relative_to(self.workspace_root)
        except ValueError as error:
            raise ValueError("path escapes workspace root") from error

    @staticmethod
    def _assert_within_workspace(workspace: Workspace, path: Path) -> None:
        try:
            path.relative_to(workspace.root)
        except ValueError as error:
            raise ValueError("path escapes challenge workspace") from error
