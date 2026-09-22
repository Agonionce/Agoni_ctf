"""Typed R6 experiment and evidence models.

Evidence records observations and provenance. It deliberately has no
``conclusion`` field: evidence may support a later conclusion, but is not the
conclusion itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping

from agent.intelligence.models import (
    ArtifactReference,
    artifact_references,
    new_id,
    utc_now_iso,
)


class ExperimentStatus(str, Enum):
    PROPOSED = "PROPOSED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass
class Experiment:
    """One bounded action proposed to test a hypothesis."""

    hypothesis_id: str
    goal: str
    action: Dict[str, Any]
    expected_result: str
    experiment_id: str = field(default_factory=lambda: new_id("experiment"))
    actual_result: str = ""
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        for name in ("experiment_id", "hypothesis_id", "goal", "expected_result"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.action, dict) or not self.action:
            raise ValueError("action must be a non-empty dictionary")
        tool_name = self.action.get("tool_name")
        arguments = self.action.get("arguments")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("action.tool_name must be a non-empty string")
        if not isinstance(arguments, Mapping):
            raise ValueError("action.arguments must be an object")
        if not isinstance(self.status, ExperimentStatus):
            raise ValueError("status must be an ExperimentStatus")

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Experiment":
        raw_action = data.get("action", {})
        if not isinstance(raw_action, Mapping):
            raise ValueError("experiment action must be an object")
        try:
            status = ExperimentStatus(str(data.get("status", ExperimentStatus.PROPOSED.value)))
        except ValueError as error:
            raise ValueError("unknown experiment status") from error
        return cls(
            experiment_id=str(data.get("experiment_id") or new_id("experiment")),
            hypothesis_id=str(data["hypothesis_id"]),
            goal=str(data["goal"]),
            action=dict(raw_action),
            expected_result=str(data["expected_result"]),
            actual_result=str(data.get("actual_result", "")),
            status=status,
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )


@dataclass
class EvidenceRecord:
    """An experiment observation with artifact provenance, never a conclusion."""

    source: str
    observation: str
    artifact_refs: list[ArtifactReference] = field(default_factory=list)
    timestamp: str = field(default_factory=utc_now_iso)
    evidence_id: str = field(default_factory=lambda: new_id("evidence"))
    experiment_id: str = ""
    hypothesis_id: str = ""
    observation_id: str = ""

    def __post_init__(self) -> None:
        for name in ("evidence_id", "source", "observation"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not all(isinstance(reference, ArtifactReference) for reference in self.artifact_refs):
            raise ValueError("artifact_refs must contain ArtifactReference values")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceRecord":
        return cls(
            evidence_id=str(data.get("evidence_id") or new_id("evidence")),
            experiment_id=str(data.get("experiment_id", "")),
            hypothesis_id=str(data.get("hypothesis_id", "")),
            observation_id=str(data.get("observation_id", "")),
            source=str(data["source"]),
            observation=str(data["observation"]),
            artifact_refs=artifact_references(data.get("artifact_refs")),
            timestamp=str(data.get("timestamp") or utc_now_iso()),
        )
