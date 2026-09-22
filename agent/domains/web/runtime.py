"""R5 Web lifecycle state integration; HTTP execution remains a Tool concern."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domains.base.runtime import DomainRuntime, DomainRuntimeState
from agent.domains.web.phases import WEB_PHASES
from agent.domains.web.intelligence.models import WebIntelligenceState
from agent.domains.web.research.manager import WebResearchManager
from agent.domains.web.state import WebRuntimeMetadata, WebRuntimeState
from agent.runtime.contracts import ChallengeSpec


class WebRuntime(DomainRuntime):
    name = "web"
    phase_definitions = WEB_PHASES

    def initialize(
        self,
        challenge: ChallengeSpec,
        restored_state: DomainRuntimeState | None = None,
    ) -> WebRuntimeState:
        if restored_state is not None:
            self._validate_state(restored_state, challenge)
            if isinstance(restored_state, WebRuntimeState):
                return restored_state
            return WebRuntimeState.from_dict(restored_state.to_dict())
        details = self.initial_details(challenge)
        base_url = challenge.metadata.get("base_url")
        raw_entries = challenge.metadata.get("entry_points", [])
        endpoints = (
            [str(item) for item in raw_entries]
            if isinstance(raw_entries, list)
            else []
        )
        state = WebRuntimeState(
            domain=self.name,
            phase=self.phase_definitions[0].name,
            challenge_id=challenge.challenge_id,
            details=details,
            base_url=str(base_url) if base_url else None,
            endpoints=sorted(set(endpoints)),
        )
        for endpoint in state.endpoints:
            state.application_model.record_endpoint(endpoint)
        return state

    def initial_details(self, challenge: ChallengeSpec) -> dict[str, Any]:
        raw_entries = challenge.metadata.get("entry_points", [])
        entries = (
            tuple(str(item) for item in raw_entries)
            if isinstance(raw_entries, list)
            else ()
        )
        session = challenge.metadata.get("session_model")
        return WebRuntimeMetadata(
            declared_entry_points=entries,
            declared_session_model=str(session) if session is not None else None,
        ).to_dict()

    def handle_observation(
        self,
        state: DomainRuntimeState,
        observation: Any,
        *,
        phase_complete: bool = False,
    ) -> DomainRuntimeState:
        updated = super().handle_observation(
            state,
            observation,
            phase_complete=phase_complete,
        )
        if not isinstance(updated, WebRuntimeState):
            return updated
        for item in self._web_observations(observation):
            base_url = item.get("base_url")
            endpoint = str(item.get("endpoint", ""))
            if isinstance(base_url, str) and base_url:
                updated.base_url = base_url
            updated.record_endpoint(endpoint)
            raw_parameters = item.get("parameters", [])
            if isinstance(raw_parameters, list):
                for parameter in raw_parameters:
                    updated.record_parameter(str(parameter), endpoint)
            raw_cookies = item.get("cookies", {})
            if isinstance(raw_cookies, Mapping):
                updated.cookies.update(
                    {str(name): str(value) for name, value in raw_cookies.items()}
                )
            raw_technologies = item.get("technologies", [])
            if isinstance(raw_technologies, list):
                for technology in raw_technologies:
                    updated.record_technology(str(technology))
        for item in self._web_intelligence_observations(observation):
            web_intelligence = WebIntelligenceState.from_dict(item)
            updated.web_intelligence.merge(web_intelligence)
            for endpoint in updated.web_intelligence.attack_surface.endpoints:
                updated.record_endpoint(endpoint.path)
                for parameter in endpoint.parameters:
                    updated.record_parameter(parameter, endpoint.path)
            for technology in updated.web_intelligence.attack_surface.technologies:
                updated.record_technology(technology)
        source = observation.get("observation") if isinstance(observation, Mapping) else observation
        analysis = observation.get("analysis") if isinstance(observation, Mapping) else None
        if hasattr(source, "tool_results"):
            WebResearchManager(updated).observe(source, analysis)
        updated.touch()
        return updated

    def generate_context(self, state: DomainRuntimeState) -> dict[str, Any]:
        self._validate_state(state)
        current = self.phase(state.phase)
        safe_state = (
            state.safe_dict() if isinstance(state, WebRuntimeState) else state.to_dict()
        )
        return {
            "domain": self.name,
            "state": safe_state,
            "phase": current.to_dict(),
        }

    @staticmethod
    def _web_observations(observation: Any) -> list[Mapping[str, Any]]:
        source = observation
        if isinstance(observation, Mapping) and "observation" in observation:
            source = observation["observation"]
        results = getattr(source, "tool_results", [])
        found: list[Mapping[str, Any]] = []
        for result in results if isinstance(results, list) else []:
            metadata = getattr(result, "metadata", {})
            web = metadata.get("web_observation") if isinstance(metadata, Mapping) else None
            if isinstance(web, Mapping):
                found.append(web)
        return found

    @staticmethod
    def _web_intelligence_observations(
        observation: Any,
    ) -> list[Mapping[str, Any]]:
        source = observation
        if isinstance(observation, Mapping) and "observation" in observation:
            source = observation["observation"]
        results = getattr(source, "tool_results", [])
        found: list[Mapping[str, Any]] = []
        for result in results if isinstance(results, list) else []:
            metadata = getattr(result, "metadata", {})
            value = (
                metadata.get("web_intelligence")
                if isinstance(metadata, Mapping)
                else None
            )
            if isinstance(value, Mapping):
                found.append(value)
        return found
