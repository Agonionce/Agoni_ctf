"""Small filesystem metadata store for artifacts produced in a Workspace."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from agent.workspace.manager import Workspace


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    path: str
    created_by: str
    created_at: str
    source_step: int
    artifact_type: str


class ArtifactStore:
    """Record artifact metadata in one challenge workspace."""

    MANIFEST_NAME = "artifacts.json"

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.manifest_path = workspace.logs_dir / self.MANIFEST_NAME
        self._artifacts: Dict[str, Artifact] = {}
        self._load()

    def register(
        self,
        path: str | Path,
        *,
        created_by: str,
        source_step: int,
        artifact_type: str = "file",
    ) -> Artifact:
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(self.workspace.root)
        except ValueError as error:
            raise ValueError("artifact path must remain inside workspace") from error
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        artifact_id = f"artifact-{len(self._artifacts) + 1:03d}"
        artifact = Artifact(
            artifact_id=artifact_id,
            path=str(relative),
            created_by=created_by,
            created_at=datetime.now(timezone.utc).isoformat(),
            source_step=source_step,
            artifact_type=artifact_type,
        )
        self._artifacts[artifact_id] = artifact
        self._persist()
        return artifact

    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self._artifacts.get(artifact_id)

    def list(self) -> List[Artifact]:
        return [self._artifacts[key] for key in sorted(self._artifacts)]

    def _load(self) -> None:
        if not self.manifest_path.exists():
            return
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        for item in raw:
            artifact = Artifact(**item)
            self._artifacts[artifact.artifact_id] = artifact

    def _persist(self) -> None:
        payload = [asdict(artifact) for artifact in self.list()]
        self.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
