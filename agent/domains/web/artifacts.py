"""JSON-serializable R5 Web request, response, and session artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RequestArtifact:
    artifact_kind: str
    request_id: str
    method: str
    url: str
    headers: dict[str, str]
    parameters: dict[str, str]
    body: str | None
    timeout: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RequestArtifact":
        raw_headers = data.get("headers", {})
        raw_parameters = data.get("parameters", {})
        return cls(
            artifact_kind=str(data.get("artifact_kind", "RequestArtifact")),
            request_id=str(data["request_id"]),
            method=str(data.get("method", "GET")).upper(),
            url=str(data["url"]),
            headers=(
                {str(name): str(value) for name, value in raw_headers.items()}
                if isinstance(raw_headers, Mapping)
                else {}
            ),
            parameters=(
                {str(name): str(value) for name, value in raw_parameters.items()}
                if isinstance(raw_parameters, Mapping)
                else {}
            ),
            body=(str(data["body"]) if data.get("body") is not None else None),
            timeout=float(data.get("timeout", 5.0)),
        )


@dataclass(frozen=True)
class ResponseArtifact:
    artifact_kind: str
    request_id: str
    url: str
    status_code: int | None
    reason: str
    headers: list[tuple[str, str]]
    body: str
    body_encoding: str
    truncated: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResponseArtifact":
        raw_headers = data.get("headers", [])
        headers: list[tuple[str, str]] = []
        if isinstance(raw_headers, list):
            for item in raw_headers:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    headers.append((str(item[0]), str(item[1])))
        status = data.get("status_code")
        return cls(
            artifact_kind=str(data.get("artifact_kind", "ResponseArtifact")),
            request_id=str(data["request_id"]),
            url=str(data["url"]),
            status_code=(int(status) if isinstance(status, int) else None),
            reason=str(data.get("reason", "")),
            headers=headers,
            body=str(data.get("body", "")),
            body_encoding=str(data.get("body_encoding", "utf-8")),
            truncated=bool(data.get("truncated", False)),
            error=(str(data["error"]) if data.get("error") is not None else None),
        )


@dataclass(frozen=True)
class SessionArtifact:
    artifact_kind: str
    request_id: str
    request_cookie_names: list[str] = field(default_factory=list)
    response_cookies: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SessionArtifact":
        raw_names = data.get("request_cookie_names", [])
        raw_cookies = data.get("response_cookies", {})
        return cls(
            artifact_kind=str(data.get("artifact_kind", "SessionArtifact")),
            request_id=str(data["request_id"]),
            request_cookie_names=(
                [str(item) for item in raw_names]
                if isinstance(raw_names, list)
                else []
            ),
            response_cookies=(
                {str(name): str(value) for name, value in raw_cookies.items()}
                if isinstance(raw_cookies, Mapping)
                else {}
            ),
        )
