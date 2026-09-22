"""Bounded Web attack-surface context for the Planner."""

from __future__ import annotations

from agent.domains.web.intelligence.models import WebAttackSurface


class WebAttackSurfaceContextBuilder:
    def __init__(
        self,
        *,
        endpoint_limit: int = 12,
        parameter_limit: int = 20,
        technology_limit: int = 12,
    ) -> None:
        for value in (endpoint_limit, parameter_limit, technology_limit):
            if value <= 0:
                raise ValueError("Web context limits must be positive")
        self.endpoint_limit = endpoint_limit
        self.parameter_limit = parameter_limit
        self.technology_limit = technology_limit

    def build(self, surface: WebAttackSurface) -> dict[str, object]:
        surface.normalize()
        return {
            "evidence_note": (
                "Endpoint and technology entries are observations, not vulnerability verdicts."
            ),
            "endpoints": [
                {
                    "path": item.path,
                    "method": item.method,
                    "parameters": item.parameters[: self.parameter_limit],
                    "source": item.source,
                    "confidence": item.confidence.value,
                }
                for item in surface.endpoints[: self.endpoint_limit]
            ],
            "parameters": surface.parameters[: self.parameter_limit],
            "technologies": surface.technologies[: self.technology_limit],
        }
