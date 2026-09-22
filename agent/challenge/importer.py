"""Challenge import coordinator for the R8.5 intake flow."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from agent.challenge.experience import (
    ChallengeExperienceManager,
    ChallengeExperiencePaths,
)
from agent.challenge.models import ChallengeManifest, utc_now_iso
from agent.challenge.workspace import (
    ChallengeWorkspaceBootstrap,
    ChallengeWorkspaceResult,
)
from agent.workspace.manager import WorkspaceManager


@dataclass(frozen=True)
class ChallengeImportResult:
    manifest: ChallengeManifest
    workspace: ChallengeWorkspaceResult
    experience: ChallengeExperiencePaths


class ChallengeImporter:
    """Validate, stage, and bind one authorized challenge without executing it."""

    def __init__(
        self,
        *,
        workspace_root: str | Path = "workspace",
        experience_root: str | Path = "experiences/challenges",
        source_root: str | Path = ".",
    ) -> None:
        self.workspace_manager = WorkspaceManager(workspace_root)
        self.experience_manager = ChallengeExperienceManager(experience_root)
        self.workspace_bootstrap = ChallengeWorkspaceBootstrap(
            self.workspace_manager,
            source_root=source_root,
        )

    def import_challenge(
        self,
        *,
        name: str,
        domain: str,
        description: str | None = None,
        description_path: str | Path | None = None,
        target_url: str | None = None,
        attachments: Sequence[str | Path] = (),
        source_paths: Sequence[str | Path] = (),
        authorization_scope: str = "authorized_ctf_only",
        created_at: str | None = None,
        entropy: str | None = None,
    ) -> ChallengeImportResult:
        if description is not None and description_path is not None:
            raise ValueError("provide description or description_path, not both")
        if description_path is not None:
            description = self.workspace_bootstrap.read_description(description_path)
        if description is None:
            raise ValueError("challenge description is required")
        manifest = ChallengeManifest.create(
            name=name,
            domain=domain,
            description=description,
            target_url=target_url,
            authorization_scope=authorization_scope,
            created_at=created_at or utc_now_iso(),
            entropy=entropy,
        )
        self.experience_manager.store.assert_available(manifest)
        prepared = self.workspace_bootstrap.prepare(attachments, source_paths)
        workspace = self.workspace_bootstrap.bootstrap(
            manifest.challenge_id,
            prepared,
        )
        manifest = replace(
            manifest,
            attachments=workspace.attachment_paths,
            source_paths=workspace.source_paths,
        )
        try:
            experience = self.experience_manager.create(
                manifest,
                imported_artifacts=workspace.artifacts,
            )
        except Exception:
            self.workspace_manager.cleanup(workspace.workspace)
            raise
        return ChallengeImportResult(
            manifest=manifest,
            workspace=workspace,
            experience=experience,
        )
