"""R8 passive Web intelligence components."""

from agent.domains.web.intelligence.behavior import ResponseBehaviorAnalyzer
from agent.domains.web.intelligence.context import WebAttackSurfaceContextBuilder
from agent.domains.web.intelligence.endpoint_mapper import EndpointMapper
from agent.domains.web.intelligence.html_analyzer import HTMLAnalyzer
from agent.domains.web.intelligence.manager import WebIntelligenceManager
from agent.domains.web.intelligence.models import (
    BehaviorFinding,
    HTMLAnalysis,
    HTMLForm,
    HypothesisProposal,
    ResponseDifference,
    TechnologyEvidence,
    WebAttackSurface,
    WebIntelligenceState,
    WebResponseProfile,
    WebStateDifference,
)
from agent.domains.web.intelligence.response import WebResponseIntelligenceAnalyzer
from agent.domains.web.intelligence.technology import TechnologyDetector

__all__ = [
    "BehaviorFinding",
    "EndpointMapper",
    "HTMLAnalysis",
    "HTMLAnalyzer",
    "HTMLForm",
    "HypothesisProposal",
    "ResponseBehaviorAnalyzer",
    "ResponseDifference",
    "TechnologyDetector",
    "TechnologyEvidence",
    "WebAttackSurface",
    "WebAttackSurfaceContextBuilder",
    "WebIntelligenceManager",
    "WebIntelligenceState",
    "WebResponseIntelligenceAnalyzer",
    "WebResponseProfile",
    "WebStateDifference",
]
