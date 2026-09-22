"""Discovery and strict validation for non-executable R3 skill assets."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from agent.domains.base import Skill, SkillPriority


class SkillValidationError(ValueError):
    """Raised when a skill asset does not satisfy the R3 contract."""


class SkillLoader:
    """Load YAML-frontmatter Markdown skills from configured directories."""

    DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "skills"
    REQUIRED_SECTIONS = ("knowledge", "strategies", "heuristics")

    def __init__(
        self,
        roots: Iterable[str | Path] | None = None,
        *,
        extra_paths: Iterable[str | Path] = (),
    ) -> None:
        initial = list(roots) if roots is not None else [self.DEFAULT_ROOT]
        self.roots = tuple(Path(path).expanduser().resolve() for path in [*initial, *extra_paths])
        self._skills: dict[str, Skill] | None = None

    def discover(self) -> list[Path]:
        files: set[Path] = set()
        for root in self.roots:
            if root.is_file() and root.suffix.lower() == ".md":
                files.add(root)
            elif root.is_dir():
                files.update(path for path in root.rglob("*.md") if path.is_file())
        return sorted(files)

    def load(self, *, refresh: bool = False) -> dict[str, Skill]:
        if self._skills is not None and not refresh:
            return dict(self._skills)
        loaded: dict[str, Skill] = {}
        for path in self.discover():
            skill = self._load_file(path)
            if skill.name in loaded:
                raise SkillValidationError(
                    f"duplicate skill name {skill.name!r}: {loaded[skill.name].source_path} and {path}"
                )
            loaded[skill.name] = skill
        self._skills = loaded
        return dict(loaded)

    def get(self, name: str) -> Skill:
        try:
            return self.load()[name]
        except KeyError as error:
            raise KeyError(f"unknown skill: {name}") from error

    def all(self) -> list[Skill]:
        return sorted(self.load().values(), key=lambda item: (item.domain, item.name))

    def for_domain(self, domain: str) -> list[Skill]:
        return [skill for skill in self.all() if skill.domain == domain]

    def _load_file(self, path: Path) -> Skill:
        raw = path.read_text(encoding="utf-8")
        metadata, body = self._frontmatter(raw, path)
        sections = self._sections(body)
        missing_sections = [name for name in self.REQUIRED_SECTIONS if not sections.get(name)]
        if missing_sections:
            raise SkillValidationError(
                f"{path}: missing non-empty sections: {', '.join(missing_sections)}"
            )

        name = self._required_text(metadata, "name", path)
        domain = self._required_text(metadata, "domain", path).lower()
        description = self._required_text(metadata, "description", path)
        tags = self._string_tuple(metadata.get("tags", ()), "tags", path)
        raw_priority = str(metadata.get("priority", "MEDIUM")).upper()
        try:
            priority = SkillPriority(raw_priority)
        except ValueError as error:
            raise SkillValidationError(f"{path}: invalid priority {raw_priority!r}") from error

        return Skill(
            name=name,
            domain=domain,
            description=description,
            knowledge=tuple(sections["knowledge"]),
            strategies=tuple(sections["strategies"]),
            heuristics=tuple(sections["heuristics"]),
            tags=tags,
            priority=priority,
            source_path=path,
        )

    @staticmethod
    def _frontmatter(raw: str, path: Path) -> tuple[Mapping[str, Any], str]:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", raw, re.DOTALL)
        if not match:
            raise SkillValidationError(f"{path}: missing YAML frontmatter")
        try:
            metadata = yaml.safe_load(match.group(1))
        except yaml.YAMLError as error:
            raise SkillValidationError(f"{path}: invalid YAML frontmatter") from error
        if not isinstance(metadata, Mapping):
            raise SkillValidationError(f"{path}: frontmatter must be a mapping")
        return metadata, raw[match.end():]

    @classmethod
    def _sections(cls, body: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {name: [] for name in cls.REQUIRED_SECTIONS}
        current: str | None = None
        for raw_line in body.splitlines():
            heading = re.match(r"^##\s+(.+?)\s*$", raw_line)
            if heading:
                candidate = heading.group(1).strip().lower()
                current = candidate if candidate in result else None
                continue
            if current is None:
                continue
            line = re.sub(r"^\s*(?:[-*+] |\d+[.)]\s+)", "", raw_line).strip()
            if line:
                result[current].append(line)
        return result

    @staticmethod
    def _required_text(metadata: Mapping[str, Any], key: str, path: Path) -> str:
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SkillValidationError(f"{path}: {key} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _string_tuple(value: Any, key: str, path: Path) -> tuple[str, ...]:
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = value
        else:
            raise SkillValidationError(f"{path}: {key} must be a string or list")
        if not all(isinstance(item, str) and item.strip() for item in values):
            raise SkillValidationError(f"{path}: {key} contains an invalid value")
        return tuple(str(item).strip().lower() for item in values)
