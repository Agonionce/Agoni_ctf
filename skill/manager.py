"""Compatibility facade over the R3 validated SkillLoader.

New runtime code should use ``agent.domains.SkillLoader`` and
``SkillContextBuilder`` directly. This module preserves the earlier query API
without retaining the unsafe "inject every skill" behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from agent.domains.loader import SkillLoader


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    content: str
    location: str


class SkillManager:
    """Read-only compatibility API backed by validated R3 skill assets."""

    def __init__(self, extra_paths: Optional[list[str]] = None) -> None:
        self.loader = SkillLoader(extra_paths=extra_paths or ())

    @staticmethod
    def _to_info(skill: object) -> SkillInfo:
        content = json.dumps(
            {
                "domain": getattr(skill, "domain"),
                "knowledge": list(getattr(skill, "knowledge")),
                "strategies": list(getattr(skill, "strategies")),
                "heuristics": list(getattr(skill, "heuristics")),
            },
            ensure_ascii=False,
            indent=2,
        )
        source_path = getattr(skill, "source_path")
        return SkillInfo(
            name=getattr(skill, "name"),
            description=getattr(skill, "description"),
            content=content,
            location=str(source_path) if isinstance(source_path, Path) else "",
        )

    def load(self) -> None:
        self.loader.load()

    def get_all(self) -> list[SkillInfo]:
        return [self._to_info(skill) for skill in self.loader.all()]

    def get(self, name: str) -> SkillInfo | None:
        try:
            return self._to_info(self.loader.get(name))
        except KeyError:
            return None

    def get_names(self) -> list[str]:
        return sorted(skill.name for skill in self.loader.all())

    def format_for_prompt(self, selected: Optional[Iterable[str]] = None) -> str:
        """Format only explicitly selected skills; never inject the full catalog."""

        names = list(selected or ())
        if not names:
            raise ValueError("explicit skill selection is required for prompt formatting")
        return json.dumps(
            [
                json.loads(self._to_info(self.loader.get(name)).content)
                | {"name": name}
                for name in names
            ],
            ensure_ascii=False,
            indent=2,
        )
