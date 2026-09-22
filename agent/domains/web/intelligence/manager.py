"""Pure coordinator for R8 Web intelligence components."""

from __future__ import annotations

from typing import Iterable
from urllib.parse import parse_qsl, urlsplit

from agent.domains.web.artifacts import (
    RequestArtifact,
    ResponseArtifact,
    SessionArtifact,
)
from agent.domains.web.intelligence.behavior import ResponseBehaviorAnalyzer
from agent.domains.web.intelligence.endpoint_mapper import EndpointMapper
from agent.domains.web.intelligence.html_analyzer import HTMLAnalyzer
from agent.domains.web.intelligence.response import WebResponseIntelligenceAnalyzer
from agent.domains.web.intelligence.models import (
    HypothesisProposal,
    WebIntelligenceState,
)
from agent.domains.web.intelligence.technology import TechnologyDetector
from agent.intelligence.models import EndpointFinding


class WebIntelligenceManager:
    """Analyze already captured artifacts; it cannot invoke Tools or networks."""

    def __init__(self) -> None:
        self.html_analyzer = HTMLAnalyzer()
        self.endpoint_mapper = EndpointMapper()
        self.technology_detector = TechnologyDetector()
        self.behavior_analyzer = ResponseBehaviorAnalyzer()
        self.response_analyzer = WebResponseIntelligenceAnalyzer()

    def analyze(
        self,
        responses: Iterable[ResponseArtifact],
        *,
        requests: Iterable[RequestArtifact] = (),
        sessions: Iterable[SessionArtifact] = (),
        existing_endpoints: Iterable[EndpointFinding] = (),
    ) -> WebIntelligenceState:
        response_items = list(responses)
        request_items = list(requests)
        session_by_request = {item.request_id: item for item in sessions}
        request_by_id = {item.request_id: item for item in request_items}

        state = WebIntelligenceState()
        state.html_analyses = [
            self.html_analyzer.analyze(item) for item in response_items
        ]
        state.attack_surface = self.endpoint_mapper.map(
            state.html_analyses,
            request_items,
            existing_endpoints,
        )
        for response in response_items:
            state.technology_evidence.extend(
                self.technology_detector.detect(
                    response,
                    session_by_request.get(response.request_id),
                )
            )
        unique_technology = {
            (item.technology, item.evidence, item.source): item
            for item in state.technology_evidence
        }
        state.technology_evidence = list(unique_technology.values())
        state.attack_surface.technologies = self.technology_detector.technologies(
            state.technology_evidence
        )
        state.response_profiles = [
            self.response_analyzer.analyze(
                response,
                request_by_id.get(response.request_id),
            )
            for response in response_items
        ]

        for baseline, current in zip(response_items, response_items[1:]):
            difference, findings = self.behavior_analyzer.compare(baseline, current)
            state.response_differences.append(difference)
            state.behavior_findings.extend(findings)
            if findings:
                proposal = self._hypothesis_for(
                    request_by_id.get(current.request_id),
                    current,
                    difference.current_errors or difference.baseline_errors,
                )
                if proposal is not None:
                    state.hypothesis_proposals.append(proposal)
        state.state_differences = [
            self.response_analyzer.compare(baseline, current)
            for baseline, current in zip(
                state.response_profiles,
                state.response_profiles[1:],
            )
        ]
        state.hypothesis_proposals = list(
            {
                item.statement: item for item in state.hypothesis_proposals
            }.values()
        )
        state.attack_surface.normalize()
        return state

    @staticmethod
    def _hypothesis_for(
        request: RequestArtifact | None,
        response: ResponseArtifact,
        evidence: Iterable[str],
    ) -> HypothesisProposal | None:
        parameters: list[str] = []
        if request is not None:
            parameters.extend(request.parameters)
            parameters.extend(
                name
                for name, _value in parse_qsl(
                    urlsplit(request.url).query,
                    keep_blank_values=True,
                )
            )
        else:
            parameters.extend(
                name
                for name, _value in parse_qsl(
                    urlsplit(response.url).query,
                    keep_blank_values=True,
                )
            )
        names = sorted(set(parameters))
        if not names:
            return None
        name = names[0]
        return HypothesisProposal(
            statement=f"Parameter {name} may influence a database query",
            confidence=0.4,
            evidence=tuple(evidence),
        )
