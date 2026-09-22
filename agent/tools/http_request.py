"""R5 structured HTTP Tool with strict loopback-only target enforcement."""

from __future__ import annotations

import http.client
import json
import re
import ssl
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agent.domains.web.artifacts import (
    RequestArtifact,
    ResponseArtifact,
    SessionArtifact,
)
from agent.domains.web.intelligence.response import WebResponseIntelligenceAnalyzer
from agent.policy.web_target import is_scoped_local_web_target, validate_local_web_target
from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
    ToolRiskLevel,
)


class HTTPRequestTool(Tool):
    """Issue one policy-reviewed request and capture three local JSON artifacts."""

    MAX_REQUEST_BYTES = 1_000_000
    MAX_RESPONSE_BYTES = 1_000_000
    MAX_TIMEOUT = 10.0
    BLOCKED_HEADERS = frozenset(
        {"host", "content-length", "connection", "transfer-encoding", "cookie"}
    )

    def __init__(self, session_manager: Any = None) -> None:
        self.session_manager = session_manager

    def bind_session_manager(self, session_manager: Any) -> None:
        """Bind runtime-owned state without allowing the session layer to execute."""

        self.session_manager = session_manager

    metadata = ToolMetadata(
        name="http_request",
        description=(
            "Send one structured GET or POST request to an R5-authorized "
            "loopback Web challenge and capture request/response/session artifacts."
        ),
        risk_level=ToolRiskLevel.MEDIUM,
        requires_network=True,
        writes_files=True,
        execution_type="http.client",
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": ["GET", "POST"]},
            "url": {"type": "string"},
            "headers": {"type": "object"},
            "cookies": {"type": "object"},
            "params": {"type": "object"},
            "body": {},
            "timeout": {"type": "number", "minimum": 0.1, "maximum": 10.0},
            "session_id": {
                "type": "string",
                "pattern": "^[A-Za-z0-9._:-]{1,128}$",
            },
        },
        "required": ["method", "url"],
        "additionalProperties": False,
    }

    def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolExecutionOutput:
        validated = self._validate(arguments, context)
        if isinstance(validated, str):
            return ToolExecutionOutput(False, error=validated)
        (
            method,
            url,
            parsed,
            headers,
            cookies,
            params,
            body_text,
            body_bytes,
            timeout,
            session_id,
        ) = validated
        if session_id:
            if self.session_manager is None:
                return ToolExecutionOutput(
                    False,
                    error="session_id requires a runtime-bound WebSessionManager",
                )
            try:
                stored_headers, stored_cookies = self.session_manager.request_state(
                    session_id,
                    url,
                )
            except ValueError as error:
                return ToolExecutionOutput(False, error=str(error))
            headers = {**stored_headers, **headers}
            cookies = {**stored_cookies, **cookies}
            for name, value in headers.items():
                if name.lower() in self.BLOCKED_HEADERS:
                    return ToolExecutionOutput(
                        False,
                        error=f"session header is managed by HTTPRequestTool: {name}",
                    )
                if (
                    re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is None
                    or self._has_control_character(name)
                    or self._has_control_character(value)
                ):
                    return ToolExecutionOutput(False, error="invalid stored session header")
            if any(
                re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is None
                or self._has_control_character(value)
                or ";" in value
                for name, value in cookies.items()
            ):
                return ToolExecutionOutput(False, error="invalid stored session cookie")
        request_id, paths = self._artifact_paths(context)
        request_headers = dict(headers)
        if cookies:
            request_headers["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in sorted(cookies.items())
            )
        if body_bytes is not None and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = (
                "application/json; charset=utf-8"
                if not isinstance(arguments.get("body"), str)
                else "text/plain; charset=utf-8"
            )
        request_artifact = RequestArtifact(
            artifact_kind="RequestArtifact",
            request_id=request_id,
            method=method,
            url=url,
            headers=self._redacted_headers(request_headers),
            parameters=params,
            body=body_text,
            timeout=timeout,
        )
        self._write_json(paths[0], request_artifact.to_dict())

        response_headers: list[tuple[str, str]] = []
        response_body = ""
        response_encoding = "utf-8"
        response_status: int | None = None
        response_reason = ""
        truncated = False
        error_message: str | None = None
        connection: http.client.HTTPConnection | None = None
        try:
            connection = self._connection(parsed, timeout)
            target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            connection.request(
                method,
                target,
                body=body_bytes,
                headers=request_headers,
            )
            response = connection.getresponse()
            response_status = response.status
            response_reason = response.reason or ""
            response_headers = response.getheaders()
            raw_body = response.read(self.MAX_RESPONSE_BYTES + 1)
            truncated = len(raw_body) > self.MAX_RESPONSE_BYTES
            raw_body = raw_body[: self.MAX_RESPONSE_BYTES]
            response_encoding = self._response_charset(response_headers)
            try:
                response_body = raw_body.decode(response_encoding, errors="replace")
            except LookupError:
                response_encoding = "utf-8"
                response_body = raw_body.decode(response_encoding, errors="replace")
        except (OSError, TimeoutError, ValueError, http.client.HTTPException) as error:
            error_message = f"HTTP request failed: {error}"
        finally:
            if connection is not None:
                connection.close()

        response_cookies = self._response_cookies(response_headers)
        session_state = None
        if session_id and self.session_manager is not None:
            try:
                session_state = self.session_manager.update_response(
                    session_id,
                    url=url,
                    method=method,
                    status_code=response_status,
                    headers=response_headers,
                    response_cookies=response_cookies,
                    body=response_body,
                )
            except ValueError as error:
                error_message = error_message or str(error)
        response_artifact = ResponseArtifact(
            artifact_kind="ResponseArtifact",
            request_id=request_id,
            url=url,
            status_code=response_status,
            reason=response_reason,
            headers=response_headers,
            body=response_body,
            body_encoding=response_encoding,
            truncated=truncated,
            error=error_message,
        )
        session_artifact = SessionArtifact(
            artifact_kind="SessionArtifact",
            request_id=request_id,
            request_cookie_names=sorted(cookies),
            response_cookies=response_cookies,
        )
        self._write_json(paths[1], response_artifact.to_dict())
        self._write_json(paths[2], session_artifact.to_dict())
        response_profile = WebResponseIntelligenceAnalyzer().analyze(
            response_artifact,
            request_artifact,
        )
        response_path = paths[1].relative_to(context.workspace_root).as_posix()

        endpoint = parsed.path or "/"
        parameter_names = sorted(
            set(params) | {name for name, _value in parse_qsl(parsed.query, keep_blank_values=True)}
        )
        reflected = sorted(
            name
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
            if name and value and value in response_body
        )
        technologies = self._technologies(response_headers)
        observation = {
            "request_id": request_id,
            "method": method,
            "url": url,
            "base_url": f"{parsed.scheme}://{parsed.netloc}",
            "endpoint": endpoint,
            "parameters": parameter_names,
            "reflected_parameters": reflected,
            "status_code": response_status,
            "technologies": technologies,
            "cookies": {
                name: "<stored-in-private-session-state>"
                for name in sorted({*cookies, *response_cookies})
            },
            "cookie_names": sorted({*cookies, *response_cookies}),
            "session_id": session_id,
            "session_status": (
                session_state.status.value if session_state is not None else ""
            ),
            "authentication_status": (
                session_state.authentication_status.value
                if session_state is not None else ""
            ),
            "response_format": response_profile.response_format,
            "content_type": response_profile.content_type,
            "json_keys": list(response_profile.json_keys),
            "error_patterns": list(response_profile.error_patterns),
            "state_markers": list(response_profile.state_markers),
            "parameter_locations": dict(response_profile.parameter_locations),
            "parameter_shapes": dict(response_profile.parameter_shapes),
            # The preview remains useful for a concise console result.  The
            # digest below is calculated from the complete captured body and
            # is the authoritative equality signal for Runtime accounting.
            "response_body_sha256": response_profile.body_sha256,
            "response_body_complete": response_profile.body_complete,
            "response_artifact_path": f"workspace://{response_path}",
            "flag_candidates": list(response_profile.flag_candidates),
            "content_signals": list(response_profile.content_signals),
            "client_request_contracts": [
                item.to_dict() for item in response_profile.client_requests
            ],
            "response_body_preview": response_body[:4096],
        }
        web_evidence = [
            {
                "evidence_type": "ENDPOINT_DISCOVERED",
                "observation": (
                    f"Endpoint {endpoint} returned status "
                    f"{response_status if response_status is not None else 'none'}"
                ),
                "request_id": request_id,
                "endpoint": endpoint,
            }
        ]
        web_evidence.extend(
            {
                "evidence_type": "PARAMETER_IDENTIFIED",
                "observation": f"Parameter {name} was observed at {endpoint}",
                "request_id": request_id,
                "endpoint": endpoint,
                "parameter": name,
            }
            for name in parameter_names
        )
        if session_id:
            web_evidence.append(
                {
                    "evidence_type": "SESSION_STATE",
                    "observation": (
                        f"Session {session_id} entered state "
                        f"{observation['session_status'] or 'ACTIVE'}"
                    ),
                    "request_id": request_id,
                    "endpoint": endpoint,
                }
            )
        error_types = set(response_profile.error_patterns)
        profile_evidence_type = "RESPONSE_BEHAVIOR"
        if error_types & {"database_error", "parser_error", "template_error", "stack_trace"}:
            profile_evidence_type = "PARSER_BEHAVIOR"
        elif error_types & {"authentication_error", "authorization_error"}:
            profile_evidence_type = "AUTHORIZATION_STATE"
        elif "file_processing_error" in error_types:
            profile_evidence_type = "FILE_PROCESSING"
        elif error_types:
            profile_evidence_type = "INPUT_BEHAVIOR"
        web_evidence.append({
            "evidence_type": profile_evidence_type,
            "observation": (
                f"Response {request_id} has format {response_profile.response_format}; "
                f"errors={','.join(response_profile.error_patterns) or 'none'}"
            ),
            "request_id": request_id,
            "endpoint": endpoint,
        })
        for contract in response_profile.client_requests:
            web_evidence.append({
                "evidence_type": "ENDPOINT_DISCOVERED",
                "observation": (
                    "Captured inline client request contract: "
                    f"{contract.method} {contract.path}"
                ),
                "request_id": request_id,
                "endpoint": contract.path,
            })
        for candidate in response_profile.flag_candidates:
            web_evidence.append({
                "evidence_type": "FLAG_CANDIDATE",
                "observation": (
                    f"Captured flag-format candidate in full response: {candidate}"
                ),
                "request_id": request_id,
                "endpoint": endpoint,
            })
        stdout = json.dumps(
            {
                "request_id": request_id,
                "url": url,
                "status_code": response_status,
                "body_preview": response_body[:2048],
                "truncated": truncated,
                "response_body_sha256": response_profile.body_sha256,
                "flag_candidates": list(response_profile.flag_candidates),
                "content_signals": list(response_profile.content_signals),
            },
            ensure_ascii=False,
        )
        artifact_types = {
            str(paths[0]): "web_request",
            str(paths[1]): "web_response",
            str(paths[2]): "web_session",
        }
        return ToolExecutionOutput(
            success=error_message is None,
            stdout=stdout,
            error=error_message,
            exit_code=0 if error_message is None else 1,
            artifact_paths=paths,
            artifact_type="web",
            artifact_types=artifact_types,
            metadata={
                "web_observation": observation,
                "web_response_profile": response_profile.to_dict(),
                "web_evidence": web_evidence,
            },
        )

    def _validate(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> tuple[Any, ...] | str:
        method = str(arguments.get("method", "")).upper()
        if method not in {"GET", "POST"}:
            return "method must be GET or POST"
        url = arguments.get("url")
        if not isinstance(url, str):
            return "url must be a string"
        target = validate_local_web_target(url)
        if not target.allowed or target.parsed is None:
            return target.reason
        if not is_scoped_local_web_target(url, context.authorized_targets):
            return "HTTP origin was not declared by the current challenge"
        headers = self._string_mapping(arguments.get("headers", {}), "headers")
        if isinstance(headers, str):
            return headers
        for name, value in headers.items():
            if name.lower() in self.BLOCKED_HEADERS:
                return f"header is managed by HTTPRequestTool: {name}"
            if re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is None:
                return f"invalid HTTP header name: {name}"
            if self._has_control_character(name) or self._has_control_character(value):
                return "headers must not contain control characters"
        cookies = self._string_mapping(arguments.get("cookies", {}), "cookies")
        if isinstance(cookies, str):
            return cookies
        if any(
            re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is None
            or self._has_control_character(value)
            or ";" in value
            for name, value in cookies.items()
        ):
            return "cookies contain an invalid name or value"
        params = self._string_mapping(arguments.get("params", {}), "params")
        if isinstance(params, str):
            return params
        parsed = target.parsed
        existing = parse_qsl(parsed.query, keep_blank_values=True)
        query = urlencode([*existing, *params.items()])
        parsed = parsed._replace(query=query)
        url = urlunsplit(parsed)
        raw_body = arguments.get("body")
        if raw_body in (None, ""):
            body_text = None
            body_bytes = None
        elif isinstance(raw_body, str):
            body_text = raw_body
            body_bytes = raw_body.encode("utf-8")
        elif isinstance(raw_body, (dict, list)):
            body_text = json.dumps(raw_body, ensure_ascii=False)
            body_bytes = body_text.encode("utf-8")
        else:
            return "body must be a string, object, array, or null"
        if body_bytes is not None and len(body_bytes) > self.MAX_REQUEST_BYTES:
            return "request body exceeds the R5 size limit"
        timeout_value = arguments.get("timeout", 5.0)
        if isinstance(timeout_value, bool) or not isinstance(timeout_value, (int, float)):
            return "timeout must be a number"
        timeout = float(timeout_value)
        if not 0.1 <= timeout <= self.MAX_TIMEOUT:
            return f"timeout must be between 0.1 and {self.MAX_TIMEOUT:g} seconds"
        session_id = arguments.get("session_id", "")
        if session_id and (
            not isinstance(session_id, str)
            or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", session_id) is None
        ):
            return "session_id must be a normalized opaque identifier"
        return (
            method,
            url,
            parsed,
            headers,
            cookies,
            params,
            body_text,
            body_bytes,
            timeout,
            str(session_id),
        )

    @staticmethod
    def _string_mapping(value: Any, name: str) -> dict[str, str] | str:
        if not isinstance(value, dict):
            return f"{name} must be an object"
        normalized: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not isinstance(item, (str, int, float, bool)):
                return f"{name} keys and values must be scalar strings"
            normalized[key] = str(item)
        return normalized

    @staticmethod
    def _has_control_character(value: str) -> bool:
        return any(ord(character) < 32 or ord(character) == 127 for character in value)

    @staticmethod
    def _connection(parsed: Any, timeout: float) -> http.client.HTTPConnection:
        hostname = parsed.hostname
        assert hostname is not None
        if parsed.scheme == "https":
            return http.client.HTTPSConnection(
                hostname,
                parsed.port or 443,
                timeout=timeout,
                context=ssl.create_default_context(),
            )
        return http.client.HTTPConnection(hostname, parsed.port or 80, timeout=timeout)

    @staticmethod
    def _redacted_headers(headers: dict[str, str]) -> dict[str, str]:
        sensitive = {"authorization", "proxy-authorization", "cookie"}
        return {
            name: "<redacted>" if name.lower() in sensitive else value
            for name, value in headers.items()
        }

    @staticmethod
    def _response_charset(headers: list[tuple[str, str]]) -> str:
        content_type = next(
            (value for name, value in headers if name.lower() == "content-type"),
            "",
        )
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.IGNORECASE)
        return match.group(1) if match else "utf-8"

    @staticmethod
    def _response_cookies(headers: list[tuple[str, str]]) -> dict[str, str]:
        found: dict[str, str] = {}
        for name, value in headers:
            if name.lower() != "set-cookie":
                continue
            cookie = SimpleCookie()
            cookie.load(value)
            found.update({key: morsel.value for key, morsel in cookie.items()})
        return found

    @staticmethod
    def _technologies(headers: list[tuple[str, str]]) -> list[str]:
        names = {"server", "x-powered-by", "x-generator"}
        return sorted(
            {value.strip() for name, value in headers if name.lower() in names and value.strip()}
        )

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _artifact_paths(context: ExecutionContext) -> tuple[str, list[Path]]:
        directory = context.output_dir / "web"
        directory.mkdir(parents=True, exist_ok=True)
        numbers = []
        for path in directory.glob("request-*.json"):
            match = re.fullmatch(r"request-(\d{3,})\.json", path.name)
            if match:
                numbers.append(int(match.group(1)))
        index = max(numbers, default=0) + 1
        request_id = f"request-{index:03d}"
        return request_id, [
            directory / f"{request_id}.json",
            directory / f"response-{index:03d}.json",
            directory / f"session-{index:03d}.json",
        ]
