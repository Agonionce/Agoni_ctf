"""Per-challenge experience folders and run binding for R8.5."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from agent.challenge.manifest import ChallengeManifestStore
from agent.challenge.models import ChallengeManifest
from agent.challenge.results import ChallengeFlagResultResolver
from agent.challenge.validator import ChallengeValidationError
from agent.challenge.writeup import WriteupTemplate
from agent.intelligence.models import IntelligenceState
from agent.runtime.contracts import RunState, to_jsonable
from agent.workspace.manager import Workspace, WorkspaceManager


@dataclass(frozen=True)
class ChallengeExperiencePaths:
    root: Path
    challenge_file: Path
    description_file: Path
    artifacts_dir: Path
    intelligence_file: Path
    experiments_file: Path
    analysis_file: Path
    report_file: Path
    writeup_file: Path
    lessons_file: Path
    lesson_candidates_file: Path
    experience_candidates_file: Path
    final_result_file: Path
    runs_dir: Path


@dataclass(frozen=True)
class ChallengeRunBinding:
    number: int
    root: Path
    checkpoint_dir: Path
    artifacts_dir: Path
    result_file: Path


class ChallengeExperienceManager:
    """Bind manifests and completed run snapshots without extracting R7 lessons."""

    def __init__(self, root: str | Path = "experiences/challenges") -> None:
        self.store = ChallengeManifestStore(root)
        self.root = self.store.root

    def create(
        self,
        manifest: ChallengeManifest,
        *,
        imported_artifacts: Iterable[Any] = (),
    ) -> ChallengeExperiencePaths:
        self.store.assert_available(manifest)
        paths = self.paths_for(manifest)
        if paths.root.exists() and any(paths.root.iterdir()):
            raise ChallengeValidationError(
                f"challenge experience directory already exists: {paths.root}"
            )
        self.store.add(manifest)
        paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
        paths.runs_dir.mkdir(parents=True, exist_ok=True)
        paths.description_file.write_text(
            f"# {manifest.name}\n\n{manifest.description}\n",
            encoding="utf-8",
        )
        self._write_json(
            paths.intelligence_file,
            IntelligenceState(challenge_id=manifest.challenge_id).to_dict(),
        )
        self._write_json(
            paths.experiments_file,
            self._experiment_snapshot(
                IntelligenceState(challenge_id=manifest.challenge_id)
            ),
        )
        paths.analysis_file.write_text(
            f"# {manifest.name} Analysis\n\n_Not started._\n",
            encoding="utf-8",
        )
        paths.report_file.write_text(
            "# Challenge Report\n\n_Not generated._\n",
            encoding="utf-8",
        )
        paths.writeup_file.write_text(
            WriteupTemplate.render(manifest.name),
            encoding="utf-8",
        )
        paths.lessons_file.write_text(
            f"# {manifest.name} Lessons\n\n_Not recorded._\n",
            encoding="utf-8",
        )
        self._write_json(
            paths.lesson_candidates_file,
            {"schema_version": 1, "challenge_id": manifest.challenge_id, "candidates": []},
        )
        self._write_json(
            paths.experience_candidates_file,
            {
                "schema_version": 1,
                "challenge_id": manifest.challenge_id,
                "candidates": [],
            },
        )
        self._write_json(
            paths.final_result_file,
            ChallengeFlagResultResolver().resolve(manifest.challenge_id, paths.runs_dir).to_dict(),
        )
        artifact_payload = [self._jsonable(item) for item in imported_artifacts]
        self._write_json(paths.artifacts_dir / "imported.json", artifact_payload)
        return paths

    def paths_for(self, manifest: ChallengeManifest) -> ChallengeExperiencePaths:
        root = self.store.directory_for(manifest)
        return ChallengeExperiencePaths(
            root=root,
            challenge_file=root / ChallengeManifestStore.MANIFEST_NAME,
            description_file=root / "description.md",
            artifacts_dir=root / "artifacts",
            intelligence_file=root / "intelligence.json",
            experiments_file=root / "experiments.json",
            analysis_file=root / "analysis.md",
            report_file=root / "report.md",
            writeup_file=root / "writeup.md",
            lessons_file=root / "lessons.md",
            lesson_candidates_file=root / "lesson_candidates.json",
            experience_candidates_file=root / "experience_candidates.json",
            final_result_file=root / "final_result.json",
            runs_dir=root / "runs",
        )

    def start_run(self, manifest: ChallengeManifest) -> ChallengeRunBinding:
        paths = self.paths_for(manifest)
        if not paths.challenge_file.is_file():
            raise FileNotFoundError(paths.challenge_file)
        paths.runs_dir.mkdir(parents=True, exist_ok=True)
        number = 1
        while (paths.runs_dir / f"run-{number:03d}").exists():
            number += 1
        root = paths.runs_dir / f"run-{number:03d}"
        checkpoint_dir = root / "checkpoint"
        artifacts_dir = root / "artifacts"
        checkpoint_dir.mkdir(parents=True, exist_ok=False)
        artifacts_dir.mkdir(parents=True, exist_ok=False)
        result_file = root / "result.md"
        result_file.write_text(
            f"# Run {number:03d}\n\nStatus: RUNNING\n",
            encoding="utf-8",
        )
        return ChallengeRunBinding(
            number=number,
            root=root,
            checkpoint_dir=checkpoint_dir,
            artifacts_dir=artifacts_dir,
            result_file=result_file,
        )

    def complete_run(
        self,
        manifest: ChallengeManifest,
        binding: ChallengeRunBinding,
        *,
        run_state: RunState,
        intelligence_state: IntelligenceState,
        artifacts: Iterable[Any],
        workspace: Workspace,
        workspace_manager: WorkspaceManager,
        checkpoint_path: str | Path | None,
        result: str,
    ) -> ChallengeRunBinding:
        if run_state.challenge.challenge_id != manifest.challenge_id:
            raise ChallengeValidationError("run state belongs to a different challenge")
        if intelligence_state.challenge_id != manifest.challenge_id:
            raise ChallengeValidationError("intelligence belongs to a different challenge")
        paths = self.paths_for(manifest)
        artifact_items = list(artifacts)
        self._write_json(paths.intelligence_file, intelligence_state.to_dict())
        self._write_json(
            paths.experiments_file,
            self._experiment_snapshot(intelligence_state),
        )
        self._write_json(binding.root / "run.json", run_state.to_dict())
        if checkpoint_path is not None:
            self._copy_checkpoint(Path(checkpoint_path), binding.checkpoint_dir)
        artifact_payload = [self._jsonable(item) for item in artifact_items]
        self._write_json(binding.artifacts_dir / "manifest.json", artifact_payload)
        latest_artifacts = paths.artifacts_dir / binding.root.name
        latest_artifacts.mkdir(parents=True, exist_ok=False)
        self._write_json(latest_artifacts / "manifest.json", artifact_payload)
        for item in artifact_items:
            relative = self._artifact_path(item)
            if relative is None:
                continue
            source = workspace_manager.resolve_path(
                workspace,
                relative,
                base=workspace.root,
            )
            if not source.is_file() or source.is_symlink():
                continue
            for destination_root in (binding.artifacts_dir, latest_artifacts):
                destination = (destination_root / relative).resolve()
                self._assert_under(destination, destination_root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        binding.result_file.write_text(
            f"# Run {binding.number:03d}\n\n"
            f"Run ID: `{run_state.run_id}`\n\n"
            f"Status: {run_state.status.value}\n\n"
            f"Artifacts: {len(artifact_items)}\n\n"
            "## Result\n\n"
            f"{result}\n",
            encoding="utf-8",
        )
        self._write_json(
            paths.final_result_file,
            ChallengeFlagResultResolver().resolve(manifest.challenge_id, paths.runs_dir).to_dict(),
        )
        return binding

    @staticmethod
    def _experiment_snapshot(state: IntelligenceState) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "challenge_id": state.challenge_id,
            "hypotheses": to_jsonable(state.hypotheses),
            "experiments": to_jsonable(state.experiments),
            "evidence": to_jsonable(state.evidence),
        }

    @staticmethod
    def _copy_checkpoint(source: Path, destination: Path) -> None:
        if not source.is_dir():
            return
        for item in sorted(source.iterdir()):
            if item.is_file() and not item.is_symlink():
                shutil.copy2(item, destination / item.name)

    @staticmethod
    def _artifact_path(item: Any) -> str | None:
        if isinstance(item, Mapping):
            value = item.get("path")
        else:
            value = getattr(item, "path", None)
        return str(value) if isinstance(value, str) and value else None

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if is_dataclass(value):
            return to_jsonable(asdict(value))
        return to_jsonable(value)

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    @staticmethod
    def _assert_under(path: Path, root: Path) -> None:
        try:
            path.relative_to(root.resolve())
        except ValueError as error:
            raise ChallengeValidationError("artifact binding escapes experience root") from error
