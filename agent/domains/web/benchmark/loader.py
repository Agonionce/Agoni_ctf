"""Contained loader for repository-owned, fake-local Web benchmark fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from agent.domains.web.benchmark.models import WebBenchmarkCase, mapping_list


class WebBenchmarkLoader:
    def __init__(self, root: str | Path = "benchmarks/web") -> None:
        self.root = Path(root).resolve()

    def list(self) -> list[WebBenchmarkCase]:
        if not self.root.is_dir():
            return []
        return [self.load(path.name) for path in sorted(self.root.iterdir())
                if path.is_dir() and (path / "challenge.json").is_file()]

    def load(self, benchmark_id: str) -> WebBenchmarkCase:
        case_root = self._contained(self.root / benchmark_id)
        challenge = self._object(case_root / "challenge.json")
        environment = self._object(case_root / "environment.json")
        expected = self._object(case_root / "expected_behavior.json")
        evaluation = self._object(case_root / "evaluation.json")
        raw_sources = challenge.get("source_files", [])
        source_files = tuple(str(item) for item in raw_sources) if isinstance(raw_sources, list) else ()
        case = WebBenchmarkCase(
            benchmark_id=str(challenge.get("benchmark_id", benchmark_id)),
            name=str(challenge.get("name", "")),
            category=str(challenge.get("category", "")),
            description=str(challenge.get("description", "")),
            source_files=source_files,
            capture_file=str(challenge.get("capture_file", "captures.json")),
            environment=dict(environment),
            expected_behavior=tuple(dict(item) for item in mapping_list(expected.get("expectations"))),
            evaluation=dict(evaluation),
        )
        if case.benchmark_id != benchmark_id:
            raise ValueError("benchmark directory and metadata ID differ")
        for relative in (*case.source_files, case.capture_file):
            path = self._contained(case_root / relative, case_root)
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"benchmark fixture is missing or unsafe: {relative}")
        return case

    def captures(self, case: WebBenchmarkCase) -> list[Mapping[str, Any]]:
        path = self._contained(self.root / case.benchmark_id / case.capture_file)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("benchmark captures must contain an object")
        captures = mapping_list(raw.get("captures"))
        if not captures:
            raise ValueError("benchmark requires at least one captured exchange")
        return captures

    def case_root(self, case: WebBenchmarkCase) -> Path:
        return self._contained(self.root / case.benchmark_id)

    def _contained(self, path: Path, root: Path | None = None) -> Path:
        resolved_root = (root or self.root).resolve()
        resolved = path.resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError as error:
            raise ValueError("benchmark path escapes the local benchmark root") from error
        return resolved

    @staticmethod
    def _object(path: Path) -> Mapping[str, Any]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError(f"benchmark JSON must contain an object: {path.name}")
        return raw
