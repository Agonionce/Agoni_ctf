"""Controlled R8 Tool adapter for passive Web artifact analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, TypeVar

from agent.domains.web.artifacts import (
    RequestArtifact,
    ResponseArtifact,
    SessionArtifact,
)
from agent.domains.web.intelligence.manager import WebIntelligenceManager
from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
    ToolRiskLevel,
)


ArtifactT = TypeVar("ArtifactT", RequestArtifact, ResponseArtifact, SessionArtifact)


class WebIntelligenceTool(Tool):
    """Analyze previously captured workspace artifacts without network access."""

    MAX_ARTIFACTS = 32
    MAX_ARTIFACT_BYTES = 2_000_000
    metadata = ToolMetadata(
        name="web_intelligence",
        description=(
            "Passively analyze captured local Web request/response artifacts for "
            "HTML structure, same-origin endpoints, technology evidence, and "
            "response differences. This tool does not send requests."
        ),
        risk_level=ToolRiskLevel.MEDIUM,
        requires_network=False,
        writes_files=True,
        execution_type="web_passive_analysis",
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {
            "response_paths": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": MAX_ARTIFACTS,
            },
            "request_paths": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_ARTIFACTS,
            },
            "session_paths": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_ARTIFACTS,
            },
        },
        "required": ["response_paths"],
        "additionalProperties": False,
    }

    def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        try:
            responses = self._load_many(
                arguments.get("response_paths"),
                context,
                ResponseArtifact,
                "ResponseArtifact",
            )
            requests = self._load_many(
                arguments.get("request_paths", []),
                context,
                RequestArtifact,
                "RequestArtifact",
            )
            sessions = self._load_many(
                arguments.get("session_paths", []),
                context,
                SessionArtifact,
                "SessionArtifact",
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            return ToolExecutionOutput(False, error=f"invalid Web artifact input: {error}")
        if not responses:
            return ToolExecutionOutput(False, error="response_paths must not be empty")

        state = WebIntelligenceManager().analyze(
            responses,
            requests=requests,
            sessions=sessions,
        )
        output_dir = context.output_dir / "web"
        output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        artifact_types: dict[str, str] = {}
        for filename, payload in state.artifact_payloads().items():
            path = output_dir / filename
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            paths.append(path)
            artifact_types[str(path)] = {
                "html-analysis.json": "web_html_analysis",
                "endpoint-map.json": "web_endpoint_map",
                "technology.json": "web_technology_evidence",
                "response-diff.json": "web_response_diff",
            }[filename]
        summary = {
            "responses_analyzed": len(responses),
            "endpoints": len(state.attack_surface.endpoints),
            "parameters": len(state.attack_surface.parameters),
            "technologies": len(state.attack_surface.technologies),
            "response_differences": len(state.response_differences),
            "response_profiles": len(state.response_profiles),
            "state_differences": len(state.state_differences),
            "hypotheses_proposed": len(state.hypothesis_proposals),
        }
        web_evidence = []
        for endpoint in state.attack_surface.endpoints[:32]:
            web_evidence.append({
                "evidence_type": "ENDPOINT_DISCOVERED",
                "observation": f"Endpoint {endpoint.method} {endpoint.path} was mapped from captured artifacts",
                "endpoint": endpoint.path,
            })
            web_evidence.extend({
                "evidence_type": "PARAMETER_IDENTIFIED",
                "observation": f"Parameter {parameter} was mapped at {endpoint.path}",
                "endpoint": endpoint.path,
                "parameter": parameter,
            } for parameter in endpoint.parameters[:16])
        for difference in state.response_differences[:16]:
            web_evidence.append({
                "evidence_type": "RESPONSE_BEHAVIOR",
                "observation": (
                    "response behavior changed "
                    f"between {difference.baseline_request_id} and "
                    f"{difference.current_request_id}: "
                    f"content_changed={difference.content_changed}; "
                    f"status_changed={difference.status_changed}"
                ),
                "request_id": difference.current_request_id,
            })
        for profile in state.response_profiles[:32]:
            error_types = set(profile.error_patterns)
            evidence_type = "RESPONSE_BEHAVIOR"
            if error_types & {"database_error", "parser_error", "template_error", "stack_trace"}:
                evidence_type = "PARSER_BEHAVIOR"
            elif error_types & {"authentication_error", "authorization_error"}:
                evidence_type = "AUTHORIZATION_STATE"
            elif "file_processing_error" in error_types:
                evidence_type = "FILE_PROCESSING"
            elif error_types:
                evidence_type = "INPUT_BEHAVIOR"
            web_evidence.append({
                "evidence_type": evidence_type,
                "observation": (
                    f"Response {profile.request_id} has format {profile.response_format}; "
                    f"errors={','.join(profile.error_patterns) or 'none'}; "
                    f"state_markers={','.join(profile.state_markers) or 'none'}"
                ),
                "request_id": profile.request_id,
            })
        for difference in state.state_differences[:16]:
            if not difference.changed:
                continue
            web_evidence.append({
                "evidence_type": "STATE_DIFFERENCE",
                "observation": (
                    f"State difference recorded between {difference.baseline_request_id} "
                    f"and {difference.current_request_id}"
                ),
                "request_id": difference.current_request_id,
            })
        return ToolExecutionOutput(
            True,
            stdout=json.dumps(summary, ensure_ascii=False),
            exit_code=0,
            artifact_paths=paths,
            artifact_type="web_intelligence",
            artifact_types=artifact_types,
            metadata={
                "web_intelligence": state.to_dict(),
                "web_evidence": web_evidence,
            },
        )

    def _load_many(
        self,
        values: Any,
        context: ExecutionContext,
        model: type[ArtifactT],
        expected_kind: str,
    ) -> list[ArtifactT]:
        if not isinstance(values, list):
            raise ValueError(f"{expected_kind} paths must be an array")
        if len(values) > self.MAX_ARTIFACTS:
            raise ValueError("too many Web artifacts")
        loaded: list[ArtifactT] = []
        for value in values:
            if not isinstance(value, str) or not value:
                raise ValueError("artifact paths must be non-empty strings")
            path = context.resolve_workspace_path(value, context.workspace_root)
            if not path.is_file():
                raise ValueError(f"artifact does not exist: {value}")
            if path.stat().st_size > self.MAX_ARTIFACT_BYTES:
                raise ValueError(f"artifact exceeds analysis limit: {value}")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError(f"artifact must contain an object: {value}")
            if payload.get("artifact_kind") != expected_kind:
                raise ValueError(f"expected {expected_kind}: {value}")
            loaded.append(model.from_dict(payload))
        return loaded
