"""Analyzer contracts and the R0 structured JSON Analyzer."""

from __future__ import annotations

from typing import Any, Dict, Protocol

from agent.intelligence.models import KnowledgeUpdateSuggestion
from agent.runtime.contracts import (
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    FlagCandidate,
    FlagCandidateKind,
    Observation,
    RunState,
)
from agent.runtime.errors import PlannerOutputError
from agent.runtime.planner import JsonRequester, parse_json_object
from agent.runtime.prompts import render_analyzer_prompt


class Analyzer(Protocol):
    """Interface consumed by AgentRuntime."""

    def analyze(self, observation: Observation, state: RunState) -> AnalysisResult:
        """Interpret structured evidence without deciding termination."""


class JsonAnalyzer:
    """Convert one JSON model response into an AnalysisResult."""

    def __init__(self, request_json: JsonRequester) -> None:
        self.request_json = request_json

    def analyze(self, observation: Observation, state: RunState) -> AnalysisResult:
        system_prompt, user_prompt = render_analyzer_prompt(observation, state)
        payload = parse_json_object(self.request_json(system_prompt, user_prompt))
        return self._result_from_payload(payload)

    @staticmethod
    def _result_from_payload(payload: Dict[str, Any]) -> AnalysisResult:
        summary = payload.get("summary")
        outcome_value = payload.get("outcome")
        if not isinstance(summary, str) or not summary.strip():
            raise PlannerOutputError("analyzer JSON missing summary")
        try:
            outcome = AnalysisOutcome(str(outcome_value))
        except (TypeError, ValueError) as error:
            raise PlannerOutputError("analyzer JSON has invalid outcome") from error

        raw_candidates = payload.get("flag_candidates", [])
        if not isinstance(raw_candidates, list):
            raise PlannerOutputError("flag_candidates must be a list")
        candidates = []
        for index, raw_candidate in enumerate(raw_candidates, start=1):
            if not isinstance(raw_candidate, dict):
                raise PlannerOutputError(f"flag candidate {index} must be an object")
            try:
                candidates.append(
                    FlagCandidate(
                        value=str(raw_candidate["value"]),
                        source=str(raw_candidate.get("source", "tool_result")),
                        confidence=float(raw_candidate.get("confidence", 0.0)),
                        evidence=str(raw_candidate["evidence"]),
                        kind=FlagCandidateKind(
                            str(raw_candidate.get("kind", "FLAG")).upper()
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise PlannerOutputError(f"invalid flag candidate {index}") from error

        confidence = float(payload.get("confidence", 0.0))
        recommendations = payload.get("recommendations", "")
        if isinstance(recommendations, list):
            recommendations = "\n".join(str(item) for item in recommendations)
        if not isinstance(recommendations, str):
            recommendations = str(recommendations)
        raw_updates = payload.get("knowledge_updates", [])
        if not isinstance(raw_updates, list):
            raise PlannerOutputError("knowledge_updates must be a list")
        try:
            knowledge_updates = [
                KnowledgeUpdateSuggestion.from_dict(update)
                for update in raw_updates
                if isinstance(update, dict)
            ]
        except ValueError as error:
            raise PlannerOutputError("invalid knowledge update suggestion") from error
        if len(knowledge_updates) != len(raw_updates):
            raise PlannerOutputError("knowledge update entries must be objects")
        return AnalysisResult(
            summary=summary,
            outcome=outcome,
            recommendations=recommendations,
            flag_candidates=candidates,
            confidence=confidence,
            knowledge_updates=knowledge_updates,
        )
