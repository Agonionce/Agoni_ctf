"""R4 contracts for declarative domain lifecycles.

Domain runtimes organize reasoning phases. They never execute Tools, inspect
targets, or contain vulnerability-specific payload logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from agent.runtime.contracts import ChallengeSpec


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PhaseDefinition:
    """Declarative phase metadata, not an executable workflow step."""

    name: str
    goal: str
    expected_observations: tuple[str, ...]
    allowed_skills: tuple[str, ...]
    next_phases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.goal.strip():
            raise ValueError("phase name and goal must be non-empty")
        if not self.expected_observations:
            raise ValueError(f"phase {self.name!r} needs expected observations")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DomainRuntimeState:
    """Small domain lifecycle state that complements, not duplicates, RunState."""

    domain: str
    phase: str
    challenge_id: str
    phase_history: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    observation_count: int = 0
    last_observation: str | None = None
    initialized_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        if not self.domain.strip() or not self.phase.strip() or not self.challenge_id.strip():
            raise ValueError("domain, phase, and challenge_id must be non-empty")
        if not self.phase_history:
            self.phase_history = [self.phase]
        if self.phase_history[-1] != self.phase:
            raise ValueError("phase_history must end at the current phase")
        if self.observation_count < 0:
            raise ValueError("observation_count must be non-negative")

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DomainRuntimeState":
        raw_history = data.get("phase_history", [])
        raw_details = data.get("details", {})
        return cls(
            domain=str(data["domain"]),
            phase=str(data["phase"]),
            challenge_id=str(data["challenge_id"]),
            phase_history=(
                [str(item) for item in raw_history]
                if isinstance(raw_history, list)
                else []
            ),
            details=dict(raw_details) if isinstance(raw_details, Mapping) else {},
            observation_count=int(data.get("observation_count", 0)),
            last_observation=(
                str(data["last_observation"])
                if data.get("last_observation") is not None
                else None
            ),
            initialized_at=str(data.get("initialized_at") or _utc_now_iso()),
            updated_at=str(data.get("updated_at") or _utc_now_iso()),
        )


class DomainRuntime(ABC):
    """Abstract lifecycle contract shared by all R4 domain runtimes."""

    name: str
    phase_definitions: tuple[PhaseDefinition, ...]

    def phases(self) -> tuple[PhaseDefinition, ...]:
        return self.phase_definitions

    def initialize(
        self,
        challenge: ChallengeSpec,
        restored_state: DomainRuntimeState | None = None,
    ) -> DomainRuntimeState:
        """Create or validate state without executing domain actions."""

        if restored_state is not None:
            self._validate_state(restored_state, challenge)
            return restored_state
        first_phase = self.phase_definitions[0]
        return DomainRuntimeState(
            domain=self.name,
            phase=first_phase.name,
            challenge_id=challenge.challenge_id,
            details=self.initial_details(challenge),
        )

    @abstractmethod
    def initial_details(self, challenge: ChallengeSpec) -> dict[str, Any]:
        """Return small domain-specific metadata copied from ChallengeSpec only."""

    def next_phase(
        self,
        state: DomainRuntimeState,
        target: str | None = None,
    ) -> DomainRuntimeState:
        """Apply one declared transition; no phase performs executable work."""

        self._validate_state(state)
        current = self.phase(state.phase)
        if not current.next_phases:
            raise ValueError(f"phase {state.phase!r} is terminal")
        destination = target or current.next_phases[0]
        if destination not in current.next_phases:
            raise ValueError(
                f"invalid {self.name} phase transition: {state.phase} -> {destination}"
            )
        self.phase(destination)
        state.phase = destination
        state.phase_history.append(destination)
        state.touch()
        return state

    def handle_observation(
        self,
        state: DomainRuntimeState,
        observation: Any,
        *,
        phase_complete: bool = False,
    ) -> DomainRuntimeState:
        """Record a bounded observation summary and optionally advance explicitly."""

        self._validate_state(state)
        state.observation_count += 1
        state.last_observation = self._observation_summary(observation)[:500]
        state.touch()
        if phase_complete:
            return self.next_phase(state)
        return state

    def generate_context(self, state: DomainRuntimeState) -> dict[str, Any]:
        """Describe the current phase for Planner context."""

        self._validate_state(state)
        current = self.phase(state.phase)
        return {
            "domain": self.name,
            "state": state.to_dict(),
            "phase": current.to_dict(),
        }

    def record_experiment_feedback(
        self,
        state: DomainRuntimeState,
        feedback: Mapping[str, Any],
        *,
        limit: int = 10,
    ) -> DomainRuntimeState:
        """Record bounded reasoning feedback without gaining Tool authority."""

        self._validate_state(state)
        if not isinstance(feedback, Mapping):
            raise ValueError("experiment feedback must be an object")
        history = state.details.get("experiment_feedback", [])
        bounded = list(history) if isinstance(history, list) else []
        experiment_id = str(feedback.get("experiment_id", ""))
        if experiment_id and any(
            isinstance(item, Mapping)
            and str(item.get("experiment_id", "")) == experiment_id
            for item in bounded
        ):
            return state
        bounded.append(dict(feedback))
        state.details["experiment_feedback"] = bounded[-limit:]
        state.touch()
        return state

    def phase(self, name: str) -> PhaseDefinition:
        try:
            return next(item for item in self.phase_definitions if item.name == name)
        except StopIteration as error:
            raise KeyError(f"unknown {self.name} phase: {name}") from error

    def _validate_state(
        self,
        state: DomainRuntimeState,
        challenge: ChallengeSpec | None = None,
    ) -> None:
        if state.domain != self.name:
            raise ValueError(
                f"runtime {self.name!r} cannot manage state for {state.domain!r}"
            )
        self.phase(state.phase)
        if challenge is not None and state.challenge_id != challenge.challenge_id:
            raise ValueError("DomainRuntimeState belongs to a different challenge")

    @staticmethod
    def _observation_summary(observation: Any) -> str:
        if isinstance(observation, Mapping):
            for key in ("summary", "objective", "kind"):
                value = observation.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for attribute in ("summary", "objective"):
            value = getattr(observation, attribute, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if isinstance(observation, str) and observation.strip():
            return observation.strip()
        return type(observation).__name__
