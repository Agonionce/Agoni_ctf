"""R4 registry and lifecycle coordinator for structure-only domain runtimes."""

from __future__ import annotations

from typing import Any, Iterable

from agent.domains.base.runtime import DomainRuntime, DomainRuntimeState
from agent.domains.crypto.runtime import CryptoRuntime
from agent.domains.misc.runtime import MiscRuntime
from agent.domains.pwn.runtime import PwnRuntime
from agent.domains.reverse.runtime import ReverseRuntime
from agent.domains.web.runtime import WebRuntime
from agent.runtime.contracts import ChallengeSpec


class DomainRuntimeManager:
    """Register, select, initialize, and route observations to one runtime."""

    def __init__(self, runtimes: Iterable[DomainRuntime] = ()) -> None:
        self._runtimes: dict[str, DomainRuntime] = {}
        self._current_runtime: DomainRuntime | None = None
        self._current_state: DomainRuntimeState | None = None
        for runtime in runtimes:
            self.register(runtime)

    def register(self, runtime: DomainRuntime) -> None:
        if runtime.name in self._runtimes:
            raise ValueError(f"duplicate domain runtime: {runtime.name}")
        if not runtime.phases():
            raise ValueError(f"domain runtime {runtime.name!r} has no phases")
        self._runtimes[runtime.name] = runtime

    def list(self) -> list[DomainRuntime]:
        return list(self._runtimes.values())

    def names(self) -> list[str]:
        return list(self._runtimes)

    def select(self, domain: str) -> DomainRuntime:
        try:
            runtime = self._runtimes[domain]
        except KeyError as error:
            raise KeyError(f"no runtime registered for domain: {domain}") from error
        self._current_runtime = runtime
        return runtime

    def initialize(
        self,
        domain: str,
        challenge: ChallengeSpec,
        restored_state: DomainRuntimeState | None = None,
    ) -> DomainRuntimeState:
        runtime = self.select(domain)
        state = runtime.initialize(challenge, restored_state)
        self._current_state = state
        return state

    def next_phase(self, target: str | None = None) -> DomainRuntimeState:
        runtime, state = self.current()
        return runtime.next_phase(state, target)

    def route_observation(
        self,
        observation: Any,
        *,
        phase_complete: bool = False,
    ) -> DomainRuntimeState:
        runtime, state = self.current()
        return runtime.handle_observation(
            state,
            observation,
            phase_complete=phase_complete,
        )

    def generate_context(self) -> dict[str, Any]:
        runtime, state = self.current()
        return runtime.generate_context(state)

    def record_experiment_feedback(
        self,
        feedback: dict[str, Any],
    ) -> DomainRuntimeState:
        runtime, state = self.current()
        return runtime.record_experiment_feedback(state, feedback)

    def current(self) -> tuple[DomainRuntime, DomainRuntimeState]:
        if self._current_runtime is None or self._current_state is None:
            raise RuntimeError("domain runtime has not been initialized")
        return self._current_runtime, self._current_state

    @property
    def current_runtime(self) -> DomainRuntime | None:
        return self._current_runtime

    @property
    def current_state(self) -> DomainRuntimeState | None:
        return self._current_state


def build_default_runtime_manager() -> DomainRuntimeManager:
    """Register the bounded R4 catalog in stable display order."""

    return DomainRuntimeManager(
        [WebRuntime(), PwnRuntime(), ReverseRuntime(), CryptoRuntime(), MiscRuntime()]
    )
