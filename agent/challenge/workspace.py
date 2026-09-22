"""Contained workspace bootstrap and input copying for Challenge Intake."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from agent.artifacts.store import Artifact, ArtifactStore
from agent.challenge.validator import ChallengeSecurityError, reject_sensitive_path
from agent.workspace.manager import Workspace, WorkspaceManager


@dataclass(frozen=True)
class PreparedInput:
    source: Path
    destination: str
    artifact_type: str


@dataclass(frozen=True)
class ChallengeWorkspaceResult:
    workspace: Workspace
    attachment_paths: tuple[str, ...]
    source_paths: tuple[str, ...]
    artifacts: tuple[Artifact, ...]


class ChallengeWorkspaceBootstrap:
    """Copy explicit local inputs through the existing WorkspaceManager boundary."""

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        *,
        source_root: str | Path,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.source_root = Path(source_root).resolve()
        if not self.source_root.is_dir():
            raise ValueError("source_root must be an existing directory")

    def read_description(self, path: str | Path, *, max_bytes: int = 1_000_000) -> str:
        source = self._resolve_source(path)
        if not source.is_file():
            raise ValueError("description file must be a regular file")
        if source.stat().st_size > max_bytes:
            raise ValueError("description file exceeds the intake size limit")
        return source.read_text(encoding="utf-8")

    def prepare(
        self,
        attachments: Sequence[str | Path],
        source_paths: Sequence[str | Path],
    ) -> tuple[PreparedInput, ...]:
        prepared: List[PreparedInput] = []
        for value in attachments:
            source = self._resolve_source(value)
            prepared.append(
                PreparedInput(
                    source,
                    (Path("input") / source.name).as_posix(),
                    "challenge_attachment",
                )
            )
        resolved_sources = [self._resolve_source(value) for value in source_paths]
        for source in resolved_sources:
            destination = (
                Path("input/source")
                if len(resolved_sources) == 1 and source.is_dir()
                else Path("input/source") / source.name
            )
            prepared.append(
                PreparedInput(
                    source,
                    destination.as_posix(),
                    "challenge_source",
                )
            )
        return tuple(prepared)

    def bootstrap(
        self,
        challenge_id: str,
        prepared: Iterable[PreparedInput],
    ) -> ChallengeWorkspaceResult:
        workspace = self.workspace_manager.create(challenge_id)
        store = ArtifactStore(workspace)
        attachment_paths: List[str] = []
        source_paths: List[str] = []
        artifacts: List[Artifact] = []
        for item in prepared:
            relative = Path(item.destination)
            destination = self.workspace_manager.resolve_path(
                workspace,
                relative,
                base=workspace.root,
            )
            if destination.exists():
                raise ValueError(f"duplicate imported path: {relative.as_posix()}")
            copied_files = self._copy(item.source, destination, workspace)
            relative_text = destination.relative_to(workspace.root).as_posix()
            if item.artifact_type == "challenge_attachment":
                attachment_paths.append(relative_text)
            else:
                source_paths.append(relative_text)
            for copied in copied_files:
                artifacts.append(
                    store.register(
                        copied,
                        created_by="challenge_import",
                        source_step=0,
                        artifact_type=item.artifact_type,
                    )
                )
        return ChallengeWorkspaceResult(
            workspace=workspace,
            attachment_paths=tuple(attachment_paths),
            source_paths=tuple(source_paths),
            artifacts=tuple(artifacts),
        )

    def _resolve_source(self, value: str | Path) -> Path:
        raw = Path(value)
        candidate = raw if raw.is_absolute() else self.source_root / raw
        if candidate.is_symlink():
            raise ChallengeSecurityError(
                "symbolic links are not accepted as challenge input"
            )
        source = candidate.resolve()
        try:
            source.relative_to(self.source_root)
        except ValueError as error:
            raise ChallengeSecurityError("input path escapes the authorized source root") from error
        if not source.exists():
            raise FileNotFoundError(source)
        try:
            source.relative_to(self.workspace_manager.workspace_root)
        except ValueError:
            pass
        else:
            raise ChallengeSecurityError("existing workspace data cannot be re-imported")
        self._validate_tree(source)
        return source

    def _validate_tree(self, source: Path) -> None:
        if source.is_symlink():
            raise ChallengeSecurityError("symbolic links are not accepted as challenge input")
        reject_sensitive_path(source)
        if source.is_dir():
            for item in source.rglob("*"):
                if item.is_symlink():
                    raise ChallengeSecurityError(
                        "symbolic links are not accepted inside challenge input"
                    )
                reject_sensitive_path(item)
                try:
                    item.resolve().relative_to(source)
                except ValueError as error:
                    raise ChallengeSecurityError("input tree escapes its source directory") from error

    def _copy(
        self,
        source: Path,
        destination: Path,
        workspace: Workspace,
    ) -> List[Path]:
        if source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return [destination]
        if not source.is_dir():
            raise ValueError(f"unsupported challenge input: {source}")
        copied: List[Path] = []
        destination.mkdir(parents=True, exist_ok=False)
        for item in sorted(source.rglob("*")):
            relative = item.relative_to(source)
            target = self.workspace_manager.resolve_path(
                workspace,
                destination.relative_to(workspace.root) / relative,
                base=workspace.root,
            )
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                copied.append(target)
        return copied
