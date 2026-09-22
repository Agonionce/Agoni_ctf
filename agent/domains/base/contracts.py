"""Typed contracts for R3 domain intelligence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from agent.runtime.contracts import ChallengeSpec

if TYPE_CHECKING:
    from agent.domains.loader import SkillLoader


class SkillPriority(str, Enum):
    """Relative ordering hint used when several relevant skills match."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class Skill:
    """Validated, non-executable domain knowledge loaded from Markdown."""

    name: str
    domain: str
    description: str
    knowledge: tuple[str, ...]
    strategies: tuple[str, ...]
    heuristics: tuple[str, ...]
    tags: tuple[str, ...] = ()
    priority: SkillPriority = SkillPriority.MEDIUM
    source_path: Path | None = None

    def __post_init__(self) -> None:
        for field_name in ("name", "domain", "description"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"skill {field_name} must be non-empty")
        for field_name in ("knowledge", "strategies", "heuristics"):
            values = getattr(self, field_name)
            if not values or not all(isinstance(item, str) and item.strip() for item in values):
                raise ValueError(f"skill {field_name} must contain non-empty guidance")


@dataclass(frozen=True)
class DomainMatch:
    """One domain's deterministic classification evidence."""

    domain: str
    confidence: float
    signals: tuple[str, ...] = ()
    matched_skills: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("domain confidence must be between 0 and 1")


class Domain(ABC):
    """Domain classifier and owner of a bounded skill catalog."""

    name: str
    description: str
    skill_names: tuple[str, ...]

    @abstractmethod
    def detect(
        self,
        challenge: ChallengeSpec,
        artifact_metadata: Sequence[Mapping[str, Any]] = (),
    ) -> DomainMatch:
        """Return a deterministic match from challenge and artifact metadata."""

    def get_skill(self, loader: "SkillLoader", name: str | None = None) -> Skill:
        """Resolve one skill owned by this domain through the validated loader."""

        selected = name or self.skill_names[0]
        if selected not in self.skill_names:
            raise KeyError(f"skill {selected!r} does not belong to domain {self.name!r}")
        skill = loader.get(selected)
        if skill.domain != self.name:
            raise ValueError(
                f"skill {selected!r} declares domain {skill.domain!r}, expected {self.name!r}"
            )
        return skill
