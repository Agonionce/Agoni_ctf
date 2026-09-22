"""Deterministic R5 Web observation extraction without vulnerability verdicts."""

from __future__ import annotations

import json
from typing import Any, Mapping

from agent.intelligence.models import ArtifactReference, KnowledgeUpdateSuggestion
from agent.runtime.analyzer import Analyzer
from agent.runtime.contracts import (
    AnalysisResult,
    FlagCandidate,
    FlagCandidateKind,
    Observation,
    RunState,
)


class WebResponseAnalyzer:
    """Convert HTTP metadata into evidence facts, never vulnerability claims."""

    def suggestions(self, observation: Observation) -> list[KnowledgeUpdateSuggestion]:
        suggestions: list[KnowledgeUpdateSuggestion] = []
        seen: set[str] = set()
        for result in observation.tool_results:
            metadata = result.metadata if isinstance(result.metadata, dict) else {}
            references = [
                ArtifactReference(artifact_id, "evidence_for")
                for artifact_id in result.artifact_refs
            ]
            intelligence = metadata.get("web_intelligence")
            if isinstance(intelligence, Mapping):
                self._append_web_intelligence(
                    suggestions,
                    seen,
                    intelligence,
                    observation.step_id,
                    references,
                )
            web = metadata.get("web_observation")
            if not isinstance(web, Mapping):
                continue
            endpoint = str(web.get("endpoint", "") or "/")
            status = web.get("status_code")
            if isinstance(status, int):
                self._append_fact(
                    suggestions,
                    seen,
                    category="endpoint",
                    content=f"endpoint={endpoint}",
                    step=observation.step_id,
                    references=references,
                )
                self._append_fact(
                    suggestions,
                    seen,
                    category="status_code",
                    content=f"status_code={status} endpoint={endpoint}",
                    step=observation.step_id,
                    references=references,
                )
            parameters = web.get("parameters", [])
            if isinstance(parameters, list):
                for name in parameters:
                    self._append_fact(
                        suggestions,
                        seen,
                        category="parameter",
                        content=f"parameter={name} endpoint={endpoint}",
                        step=observation.step_id,
                        references=references,
                    )
            reflected = web.get("reflected_parameters", [])
            if isinstance(reflected, list):
                for name in reflected:
                    self._append_fact(
                        suggestions,
                        seen,
                        category="reflection",
                        content=f"reflection={name} endpoint={endpoint}",
                        step=observation.step_id,
                        references=references,
                    )
            technologies = web.get("technologies", [])
            if isinstance(technologies, list):
                for technology in technologies:
                    self._append_fact(
                        suggestions,
                        seen,
                        category="technology",
                        content=f"technology={technology}",
                        step=observation.step_id,
                        references=references,
                    )
            response_format = str(web.get("response_format", ""))
            if response_format:
                self._append_fact(
                    suggestions,
                    seen,
                    category="response_format",
                    content=f"response_format={response_format} endpoint={endpoint}",
                    step=observation.step_id,
                    references=references,
                )
            for pattern in web.get("error_patterns", []) if isinstance(
                web.get("error_patterns"), list
            ) else []:
                self._append_fact(
                    suggestions,
                    seen,
                    category="error_pattern",
                    content=f"error_pattern={pattern} endpoint={endpoint}",
                    step=observation.step_id,
                    references=references,
                )
            for contract in web.get("client_request_contracts", []) if isinstance(
                web.get("client_request_contracts"), list
            ) else []:
                if not isinstance(contract, Mapping):
                    continue
                self._append_fact(
                    suggestions,
                    seen,
                    category="client_request_contract",
                    content=self._contract_summary(contract),
                    step=observation.step_id,
                    references=references,
                )
        return suggestions

    @staticmethod
    def flag_candidates(observation: Observation) -> list[FlagCandidate]:
        """Promote only deterministic full-response candidates to the Flag path."""

        candidates: list[FlagCandidate] = []
        seen: set[str] = set()
        for result in observation.tool_results:
            metadata = result.metadata if isinstance(result.metadata, dict) else {}
            web = metadata.get("web_observation")
            if not isinstance(web, Mapping):
                continue
            values = web.get("flag_candidates", [])
            if not isinstance(values, list):
                continue
            request_id = str(web.get("request_id", "captured response"))
            for value in values:
                token = str(value).strip()
                if not token or token in seen:
                    continue
                seen.add(token)
                candidates.append(
                    FlagCandidate(
                        value=token,
                        source=f"captured full HTTP response {request_id}",
                        confidence=0.99,
                        evidence=(
                            f"deterministic flag-format match in response {request_id}; "
                            f"digest={web.get('response_body_sha256', '')}"
                        ),
                        kind=FlagCandidateKind.FLAG,
                    )
                )
        return candidates

    @staticmethod
    def guidance(observation: Observation) -> str:
        """Return bounded evidence-first re-planning guidance for the Planner."""

        messages: list[str] = []
        for result in observation.tool_results:
            metadata = result.metadata if isinstance(result.metadata, dict) else {}
            web = metadata.get("web_observation")
            if not isinstance(web, Mapping):
                continue
            artifact_path = web.get("response_artifact_path")
            if isinstance(artifact_path, str) and artifact_path:
                messages.append(
                    "The complete captured response is available at "
                    f"{artifact_path}; inspect it with the passive Web intelligence path "
                    "before inventing unrelated request variants."
                )
            contracts = web.get("client_request_contracts", [])
            if not isinstance(contracts, list):
                continue
            for contract in contracts[:4]:
                if isinstance(contract, Mapping):
                    messages.append(
                        "Use this observed browser request contract as the starting shape "
                        "for any next controlled action: "
                        f"{WebResponseAnalyzer._contract_summary(contract)}."
                    )
        return " ".join(dict.fromkeys(messages))[:2000]

    @staticmethod
    def _contract_summary(contract: Mapping[str, Any]) -> str:
        method = str(contract.get("method", "GET")).upper()
        path = str(contract.get("path", "/"))
        query = contract.get("query", [])
        json_body = contract.get("json_body", [])
        rendered_query = "&".join(
            f"{item[0]}={item[1]}"
            for item in query
            if isinstance(item, (list, tuple)) and len(item) == 2
        )
        rendered_body = ", ".join(
            f"{item[0]}={item[1]}"
            for item in json_body
            if isinstance(item, (list, tuple)) and len(item) == 2
        )
        target = f"{path}?{rendered_query}" if rendered_query else path
        return (
            f"method={method}; endpoint={target}; "
            f"json_body={rendered_body or 'none'}"
        )

    @staticmethod
    def _append_web_intelligence(
        suggestions: list[KnowledgeUpdateSuggestion],
        seen: set[str],
        intelligence: Mapping[str, Any],
        step: int,
        references: list[ArtifactReference],
    ) -> None:
        raw_surface = intelligence.get("attack_surface", {})
        if isinstance(raw_surface, Mapping):
            raw_endpoints = raw_surface.get("endpoints", [])
            for endpoint in raw_endpoints if isinstance(raw_endpoints, list) else []:
                if not isinstance(endpoint, Mapping):
                    continue
                payload = {
                    "path": str(endpoint.get("path", "")),
                    "method": str(endpoint.get("method", "GET")),
                    "parameters": endpoint.get("parameters", []),
                    "source": str(endpoint.get("source", "web intelligence")),
                    "confidence": str(endpoint.get("confidence", "MEDIUM")),
                }
                WebResponseAnalyzer._append_suggestion(
                    suggestions,
                    seen,
                    "endpoint_finding",
                    payload,
                    step,
                    references,
                )
        raw_technology = intelligence.get("technology_evidence", [])
        for item in raw_technology if isinstance(raw_technology, list) else []:
            if not isinstance(item, Mapping):
                continue
            technology = str(item.get("technology", ""))
            evidence = str(item.get("evidence", ""))
            if technology and evidence:
                WebResponseAnalyzer._append_suggestion(
                    suggestions,
                    seen,
                    "fact",
                    {
                        "category": "technology_evidence",
                        "content": f"technology={technology}; evidence={evidence}",
                        "confidence": str(item.get("confidence", "MEDIUM")),
                    },
                    step,
                    references,
                )
        raw_findings = intelligence.get("behavior_findings", [])
        for item in raw_findings if isinstance(raw_findings, list) else []:
            if isinstance(item, Mapping) and item.get("title"):
                WebResponseAnalyzer._append_suggestion(
                    suggestions,
                    seen,
                    "finding",
                    {
                        "title": str(item["title"]),
                        "description": str(item.get("description", "")),
                        "importance": "MEDIUM",
                    },
                    step,
                    references,
                )
        raw_hypotheses = intelligence.get("hypothesis_proposals", [])
        for item in raw_hypotheses if isinstance(raw_hypotheses, list) else []:
            if isinstance(item, Mapping) and item.get("statement"):
                WebResponseAnalyzer._append_suggestion(
                    suggestions,
                    seen,
                    "hypothesis",
                    {
                        "statement": str(item["statement"]),
                        "domain": "web",
                        "confidence": float(item.get("confidence", 0.4)),
                        "status": "OPEN",
                    },
                    step,
                    references,
                )
        raw_profiles = intelligence.get("response_profiles", [])
        for item in raw_profiles if isinstance(raw_profiles, list) else []:
            if not isinstance(item, Mapping):
                continue
            request_id = str(item.get("request_id", ""))
            response_format = str(item.get("response_format", "TEXT"))
            json_keys = item.get("json_keys", [])
            errors = item.get("error_patterns", [])
            WebResponseAnalyzer._append_suggestion(
                suggestions,
                seen,
                "fact",
                {
                    "category": "response_structure",
                    "content": (
                        f"request={request_id}; format={response_format}; "
                        f"json_keys={','.join(str(value) for value in json_keys[:16]) if isinstance(json_keys, list) else ''}; "
                        f"error_patterns={','.join(str(value) for value in errors[:8]) if isinstance(errors, list) else ''}"
                    ),
                    "confidence": "CONFIRMED",
                },
                step,
                references,
            )
            parameters = item.get("parameter_names", [])
            if isinstance(errors, list) and errors and isinstance(parameters, list) and parameters:
                WebResponseAnalyzer._append_suggestion(
                    suggestions,
                    seen,
                    "hypothesis",
                    {
                        "statement": (
                            f"Parameter {parameters[0]} may influence the observed parser behavior."
                        ),
                        "domain": "web",
                        "confidence": 0.4,
                        "status": "OPEN",
                        "experiment_goal": "characterize the parser response using bounded local evidence",
                        "expected_result": "parser behavior difference recorded",
                        "experiment_type": "PARSER_BEHAVIOR_ANALYSIS",
                        "evidence_type": "PARSER_BEHAVIOR",
                    },
                    step,
                    references,
                )
        raw_state_differences = intelligence.get("state_differences", [])
        for item in raw_state_differences if isinstance(raw_state_differences, list) else []:
            if not isinstance(item, Mapping) or not bool(item.get("changed", False)):
                continue
            WebResponseAnalyzer._append_suggestion(
                suggestions,
                seen,
                "finding",
                {
                    "title": "Web response state difference",
                    "description": (
                        f"Captured responses {item.get('baseline_request_id', '')} and "
                        f"{item.get('current_request_id', '')} differ structurally."
                    ),
                    "importance": "MEDIUM",
                },
                step,
                references,
            )

    @staticmethod
    def _append_suggestion(
        suggestions: list[KnowledgeUpdateSuggestion],
        seen: set[str],
        kind: str,
        payload: dict[str, Any],
        step: int,
        references: list[ArtifactReference],
    ) -> None:
        identity = json.dumps([kind, payload], ensure_ascii=False, sort_keys=True)
        if identity in seen:
            return
        seen.add(identity)
        suggestions.append(
            KnowledgeUpdateSuggestion(
                kind=kind,
                payload=payload,
                source_step=step,
                artifact_refs=references,
            )
        )

    @staticmethod
    def _append_fact(
        suggestions: list[KnowledgeUpdateSuggestion],
        seen: set[str],
        *,
        category: str,
        content: str,
        step: int,
        references: list[ArtifactReference],
    ) -> None:
        identity = json.dumps([category, content], ensure_ascii=False)
        if identity in seen:
            return
        seen.add(identity)
        suggestions.append(
            KnowledgeUpdateSuggestion(
                kind="fact",
                payload={
                    "category": category,
                    "content": content,
                    "confidence": "CONFIRMED",
                },
                source_step=step,
                artifact_refs=references,
            )
        )


class WebIntelligenceAnalyzer:
    """Decorate the existing Analyzer with deterministic HTTP fact extraction."""

    def __init__(self, delegate: Analyzer) -> None:
        self.delegate = delegate
        self.extractor = WebResponseAnalyzer()

    def analyze(self, observation: Observation, state: RunState) -> AnalysisResult:
        result = self.delegate.analyze(observation, state)
        existing = {
            json.dumps(
                [suggestion.kind, suggestion.payload],
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            for suggestion in result.knowledge_updates
        }
        for suggestion in self.extractor.suggestions(observation):
            identity = json.dumps(
                [suggestion.kind, suggestion.payload],
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            if identity not in existing:
                result.knowledge_updates.append(suggestion)
                existing.add(identity)
        existing_candidates = {item.value for item in result.flag_candidates}
        for candidate in self.extractor.flag_candidates(observation):
            if candidate.value not in existing_candidates:
                result.flag_candidates.append(candidate)
                existing_candidates.add(candidate.value)
        guidance = self.extractor.guidance(observation)
        if guidance and guidance not in result.recommendations:
            result.recommendations = " ".join(
                part for part in (result.recommendations.strip(), guidance) if part
            )
        return result
