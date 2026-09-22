"""Challenge catalog projection and existing Intake coordination."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from agent.challenge.experience import ChallengeExperienceManager
from agent.challenge.importer import ChallengeImporter
from agent.challenge.models import ChallengeManifest
from agent.challenge.validator import challenge_name_key
from webui.models import ChallengeDetail, ChallengeMaterial, ChallengeSummary


STATUS_LABELS = {
    "not_started": "未开始",
    "analyzing": "分析中",
    "waiting": "等待确认",
    "needs_help": "需要帮助",
    "completed": "已完成",
    "not_solved": "未解决",
    "paused": "已暂停",
}


@dataclass(frozen=True)
class UISettings:
    """Local paths and bounded upload settings supplied by the host."""

    workspace_root: Path = Path("workspace")
    experience_root: Path = Path("experiences/challenges")
    global_experience_path: Path = Path("experiences/global/experience.json")
    checkpoint_root: Path = Path(".runtime/webui-runs")
    staging_root: Path = Path(".runtime/webui-staging")
    max_file_bytes: int = 64 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_uploads: int = 64

    def normalized(self) -> "UISettings":
        if self.max_file_bytes <= 0 or self.max_total_bytes <= 0:
            raise ValueError("upload limits must be positive")
        if self.max_uploads <= 0:
            raise ValueError("max_uploads must be positive")
        return UISettings(
            workspace_root=self.workspace_root.resolve(),
            experience_root=self.experience_root.resolve(),
            global_experience_path=self.global_experience_path.resolve(),
            checkpoint_root=self.checkpoint_root.resolve(),
            staging_root=self.staging_root.resolve(),
            max_file_bytes=self.max_file_bytes,
            max_total_bytes=self.max_total_bytes,
            max_uploads=self.max_uploads,
        )


class DuplicateChallengeError(ValueError):
    def __init__(self, challenge_id: str) -> None:
        super().__init__("同名题目已存在")
        self.challenge_id = challenge_id


class ChallengeCatalogService:
    """Expose concise projections and delegate writes to ChallengeImporter."""

    def __init__(self, settings: UISettings) -> None:
        self.settings = settings.normalized()
        self.manager = ChallengeExperienceManager(self.settings.experience_root)

    def list(self) -> list[ChallengeSummary]:
        manifests = reversed(self.manager.store.list())
        return [self._summary(item) for item in manifests]

    def get(self, challenge_id: str) -> ChallengeDetail | None:
        manifest = self.manager.store.get(challenge_id)
        if manifest is None:
            return None
        summary = self._summary(manifest)
        return ChallengeDetail(
            **summary.model_dump(),
            description=self._display_text(manifest.description),
            target_url=self._display_target(manifest.target_url),
            materials=self._materials(manifest),
        )

    def create(
        self,
        *,
        name: str,
        description: str,
        domain: str,
        target_url: str | None,
        source_root: Path,
        attachments: list[Path],
        source_files: list[Path],
    ) -> ChallengeDetail:
        existing = self._existing_for_name(name)
        if existing is not None:
            raise DuplicateChallengeError(existing.challenge_id)
        result = ChallengeImporter(
            workspace_root=self.settings.workspace_root,
            experience_root=self.settings.experience_root,
            source_root=source_root,
        ).import_challenge(
            name=name,
            description=description,
            domain=domain,
            target_url=target_url,
            attachments=attachments,
            source_paths=source_files,
            authorization_scope="authorized_ctf_only",
        )
        detail = self.get(result.manifest.challenge_id)
        if detail is None:
            raise RuntimeError("created challenge could not be loaded")
        return detail

    def _existing_for_name(self, name: str) -> ChallengeManifest | None:
        try:
            normalized = challenge_name_key(name)
        except ValueError:
            return None
        return next(
            (
                item
                for item in self.manager.store.list()
                if challenge_name_key(item.name) == normalized
            ),
            None,
        )

    def _summary(self, manifest: ChallengeManifest) -> ChallengeSummary:
        status = self._status(manifest)
        return ChallengeSummary(
            challenge_id=manifest.challenge_id,
            name=self._display_text(manifest.name),
            domain=manifest.domain,
            status=status,
            status_label=STATUS_LABELS[status],
            created_at=manifest.created_at,
        )

    @staticmethod
    def _display_text(value: object) -> str:
        """Return challenge-local text verbatim for the authorized operator."""

        return str(value).strip()

    @staticmethod
    def _display_target(value: str | None) -> str | None:
        return str(value).strip() if value else None

    def _status(self, manifest: ChallengeManifest) -> str:
        paths = self.manager.paths_for(manifest)
        runs = sorted(
            (item for item in paths.runs_dir.glob("run-*") if item.is_dir()),
            key=lambda item: item.name,
        )
        if not runs:
            return "not_started"
        latest = runs[-1]
        run_file = latest / "run.json"
        if not run_file.is_file():
            return "analyzing"
        try:
            payload = json.loads(run_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "needs_help"
        raw_status = str(payload.get("status", "")).upper()
        mapping = {
            "CREATED": "not_started",
            "RUNNING": "analyzing",
            "SOLVED": "completed",
            "BLOCKED": "needs_help",
            "FAILED": "not_solved",
            "BUDGET_EXHAUSTED": "not_solved",
            "ABORTED": "paused",
            "PAUSED": "paused",
        }
        return mapping.get(raw_status, "needs_help")

    def _materials(self, manifest: ChallengeManifest) -> list[ChallengeMaterial]:
        imported = self.manager.paths_for(manifest).artifacts_dir / "imported.json"
        raw_items: list[Mapping[str, Any]] = []
        try:
            payload = json.loads(imported.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                raw_items = [item for item in payload if isinstance(item, Mapping)]
        except (OSError, json.JSONDecodeError):
            raw_items = []
        materials: list[ChallengeMaterial] = []
        seen: set[tuple[str, str]] = set()
        for item in raw_items:
            raw_path = item.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                continue
            artifact_type = str(item.get("artifact_type", ""))
            kind = "attachment" if artifact_type == "challenge_attachment" else "source"
            name = raw_path
            key = (name, kind)
            if key in seen:
                continue
            seen.add(key)
            materials.append(ChallengeMaterial(name=name, kind=kind))
        return materials
