"""Filesystem catalog for ChallengeManifest records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from agent.challenge.models import ChallengeManifest
from agent.challenge.validator import ChallengeValidationError, slugify_name


class ChallengeManifestStore:
    """Persist one manifest below each ignored challenge experience directory."""

    MANIFEST_NAME = "challenge.json"

    def __init__(self, root: str | Path = "experiences/challenges") -> None:
        self.root = Path(root).resolve()

    def directory_for(self, manifest: ChallengeManifest) -> Path:
        directory = (self.root / slugify_name(manifest.name)).resolve()
        self._assert_under_root(directory)
        return directory

    def assert_available(self, manifest: ChallengeManifest) -> None:
        path = self.directory_for(manifest) / self.MANIFEST_NAME
        if path.exists():
            existing = self._load_path(path)
            if existing.challenge_id != manifest.challenge_id:
                raise ChallengeValidationError(
                    f"challenge name already exists: {manifest.name}; reuse ID "
                    f"{existing.challenge_id} for another run"
                )

    def add(self, manifest: ChallengeManifest) -> Path:
        self.assert_available(manifest)
        directory = self.directory_for(manifest)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / self.MANIFEST_NAME
        self._write_json(path, manifest.to_dict())
        return path

    def get(self, challenge_id: str) -> ChallengeManifest | None:
        normalized = challenge_id.strip()
        if not normalized:
            return None
        for path in self._manifest_paths():
            manifest = self._load_path(path)
            if manifest.challenge_id == normalized:
                return manifest
        return None

    def list(self) -> List[ChallengeManifest]:
        manifests = [self._load_path(path) for path in self._manifest_paths()]
        return sorted(manifests, key=lambda item: (item.created_at, item.challenge_id))

    def path_for_id(self, challenge_id: str) -> Path | None:
        for path in self._manifest_paths():
            if self._load_path(path).challenge_id == challenge_id:
                return path
        return None

    def _manifest_paths(self) -> List[Path]:
        if not self.root.exists():
            return []
        return sorted(self.root.glob(f"*/{self.MANIFEST_NAME}"))

    @staticmethod
    def _load_path(path: Path) -> ChallengeManifest:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"challenge manifest must be a JSON object: {path}")
        return ChallengeManifest.from_dict(raw)

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _assert_under_root(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise ChallengeValidationError("challenge path escapes experience root") from error
