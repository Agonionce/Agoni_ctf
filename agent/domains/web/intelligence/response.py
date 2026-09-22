"""R12 passive HTML/JSON/error/state response understanding."""

from __future__ import annotations

import json
import hashlib
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from agent.domains.web.artifacts import RequestArtifact, ResponseArtifact
from agent.domains.web.intelligence.html_analyzer import HTMLAnalyzer
from agent.domains.web.intelligence.models import (
    WebResponseProfile,
    WebStateDifference,
)


class WebResponseIntelligenceAnalyzer:
    """Describe captured responses without executing content or claiming a flaw."""

    MAX_JSON_KEYS = 64
    MAX_FLAG_CANDIDATES = 8
    FLAG_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_-]{0,63}\{[^{}\s]{1,512}\}")
    ERROR_PATTERNS = {
        "database_error": re.compile(r"(?:sql|sqlite|database|db)\s*(?:error|exception|failed)", re.I),
        "parser_error": re.compile(r"(?:parse|parser|json|xml|yaml)\s*(?:error|exception|failed|invalid)", re.I),
        "template_error": re.compile(r"(?:template|render)\s*(?:error|exception|failed)", re.I),
        "file_processing_error": re.compile(
            r"(?:(?:file|upload|image|archive)\s*(?:error|invalid|failed)|"
            r"(?:文件|路径).{0,16}(?:不存在|无法|错误)|不存在或无法解析)",
            re.I,
        ),
        "validation_error": re.compile(r"(?:validation|invalid input|required field)", re.I),
        "authentication_error": re.compile(r"(?:unauthorized|authentication required|login required)", re.I),
        "authorization_error": re.compile(r"(?:forbidden|permission denied|access denied)", re.I),
        "stack_trace": re.compile(r"(?:traceback \(most recent call last\)|stack trace|unhandled exception)", re.I),
    }
    STATE_PATTERNS = {
        "anonymous": re.compile(r"\b(?:anonymous|guest)\b", re.I),
        "authenticated": re.compile(r"\b(?:authenticated|logged in|signed in)\b", re.I),
        "authorization_challenged": re.compile(r"\b(?:forbidden|access denied|permission denied)\b", re.I),
        "success": re.compile(r"\b(?:success|completed|accepted)\b", re.I),
        "failure": re.compile(r"\b(?:failed|failure|rejected)\b", re.I),
        "state_changed": re.compile(r"\b(?:updated|created|deleted|added|removed)\b", re.I),
    }

    def analyze(
        self,
        response: ResponseArtifact,
        request: RequestArtifact | None = None,
    ) -> WebResponseProfile:
        content_type = self._content_type(response.headers)
        parsed_json = self._json(response.body, content_type)
        response_format = self._format(response.body, content_type, parsed_json)
        html = HTMLAnalyzer().analyze(response) if response_format == "HTML" else None
        locations, shapes = self._parameters(request)
        flag_candidates = tuple(
            dict.fromkeys(self.FLAG_PATTERN.findall(response.body))
        )[: self.MAX_FLAG_CANDIDATES]
        content_signals: list[str] = []
        if flag_candidates:
            content_signals.append("flag_candidate")
        if html is not None and html.client_requests:
            content_signals.append("client_request_contract")
        if response.error:
            content_signals.append("transport_error")
        if any(pattern.search(response.body[:1_000_000]) for pattern in self.ERROR_PATTERNS.values()):
            content_signals.append("error_message")
        return WebResponseProfile(
            request_id=response.request_id,
            url=response.url,
            status_code=response.status_code,
            content_type=content_type,
            response_format=response_format,
            body_length=len(response.body),
            json_keys=tuple(self._json_keys(parsed_json)) if parsed_json is not None else (),
            error_patterns=tuple(
                name for name, pattern in self.ERROR_PATTERNS.items()
                if pattern.search(response.body[:1_000_000])
            ),
            state_markers=tuple(
                name for name, pattern in self.STATE_PATTERNS.items()
                if pattern.search(response.body[:1_000_000])
            ),
            html_form_count=len(html.forms) if html is not None else 0,
            html_link_count=len(html.links) if html is not None else 0,
            parameter_names=tuple(sorted(locations)),
            parameter_locations=tuple(sorted(locations.items())),
            parameter_shapes=tuple(sorted(shapes.items())),
            body_sha256=hashlib.sha256(response.body.encode("utf-8")).hexdigest(),
            body_complete=not response.truncated,
            flag_candidates=flag_candidates,
            content_signals=tuple(content_signals),
            client_requests=html.client_requests if html is not None else (),
        )

    @staticmethod
    def compare(
        baseline: WebResponseProfile,
        current: WebResponseProfile,
    ) -> WebStateDifference:
        def changes(before: tuple[str, ...], after: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
            return tuple(sorted(set(after) - set(before))), tuple(sorted(set(before) - set(after)))
        keys_added, keys_removed = changes(baseline.json_keys, current.json_keys)
        errors_added, errors_removed = changes(baseline.error_patterns, current.error_patterns)
        states_added, states_removed = changes(baseline.state_markers, current.state_markers)
        return WebStateDifference(
            baseline_request_id=baseline.request_id,
            current_request_id=current.request_id,
            status_changed=baseline.status_code != current.status_code,
            format_changed=baseline.response_format != current.response_format,
            json_keys_added=keys_added,
            json_keys_removed=keys_removed,
            errors_added=errors_added,
            errors_removed=errors_removed,
            state_markers_added=states_added,
            state_markers_removed=states_removed,
        )

    @staticmethod
    def _content_type(headers: list[tuple[str, str]]) -> str:
        return next(
            (value.split(";", 1)[0].strip().lower()
             for name, value in headers if name.lower() == "content-type"),
            "",
        )

    @staticmethod
    def _json(body: str, content_type: str) -> Any:
        stripped = body.lstrip()
        if "json" not in content_type and not stripped.startswith(("{", "[")):
            return None
        try:
            return json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _format(body: str, content_type: str, parsed_json: Any) -> str:
        if parsed_json is not None:
            return "JSON"
        lowered = body[:1000].lower()
        if "html" in content_type or "<html" in lowered or "<!doctype html" in lowered:
            return "HTML"
        if content_type.startswith(("image/", "audio/", "video/", "application/octet-stream")):
            return "BINARY"
        return "TEXT"

    def _json_keys(self, value: Any, prefix: str = "", depth: int = 0) -> list[str]:
        if depth > 3:
            return []
        keys: list[str] = []
        if isinstance(value, Mapping):
            for name, item in value.items():
                path = f"{prefix}.{name}" if prefix else str(name)
                keys.append(path[:200])
                if len(keys) >= self.MAX_JSON_KEYS:
                    break
                keys.extend(self._json_keys(item, path, depth + 1))
        elif isinstance(value, list) and value:
            path = f"{prefix}[]" if prefix else "[]"
            keys.extend(self._json_keys(value[0], path, depth + 1))
        return list(dict.fromkeys(keys))[: self.MAX_JSON_KEYS]

    @staticmethod
    def _parameters(request: RequestArtifact | None) -> tuple[dict[str, str], dict[str, str]]:
        if request is None:
            return {}, {}
        query = dict(parse_qsl(urlsplit(request.url).query, keep_blank_values=True))
        locations: dict[str, str] = {name: "query" for name in query}
        shapes: dict[str, str] = {
            name: WebResponseIntelligenceAnalyzer._shape(value)
            for name, value in query.items()
        }
        for name, value in request.parameters.items():
            locations[name] = locations.get(name, "request")
            shapes[name] = WebResponseIntelligenceAnalyzer._shape(value)
        if request.body:
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                body = None
            if isinstance(body, Mapping):
                for name, value in body.items():
                    locations[str(name)] = "json"
                    shapes[str(name)] = WebResponseIntelligenceAnalyzer._shape(value)
        return locations, shapes

    @staticmethod
    def _shape(value: Any) -> str:
        text = str(value).strip()
        if not text:
            return "empty"
        if re.fullmatch(r"-?\d+", text):
            return "integer"
        if text.lower() in {"true", "false"}:
            return "boolean"
        if text.startswith(("http://", "https://")):
            return "url"
        if "/" in text or "\\" in text:
            return "path-like"
        if text.startswith(("{", "[")):
            return "structured"
        return "text"
