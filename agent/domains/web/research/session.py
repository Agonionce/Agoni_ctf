"""Contained Web session lifecycle used by the controlled HTTP Tool."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlsplit

from agent.domains.web.research.models import (
    AuthenticationStatus,
    WebSessionState,
    WebSessionStatus,
)
from agent.intelligence.models import utc_now_iso
from agent.policy.web_target import validate_local_web_target


class _CsrfInputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = {name.lower(): value or "" for name, value in attrs}
        name = values.get("name", "")
        if name and re.search(r"(?:csrf|xsrf|authenticity|_token)", name, re.I):
            value = values.get("value", "")
            if value:
                self.tokens[name] = value


class WebSessionManager:
    """Own session state; it never sends an HTTP request itself."""

    def __init__(self, sessions: list[WebSessionState]) -> None:
        self.sessions = sessions

    def create(self, origin: str, *, session_id: str = "") -> WebSessionState:
        validation = validate_local_web_target(origin)
        if not validation.allowed or validation.parsed is None:
            raise ValueError(validation.reason)
        normalized_origin = self._origin(origin)
        identifier = session_id or f"session-{len(self.sessions) + 1:03d}"
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", identifier) is None:
            raise ValueError("session_id must be a normalized opaque identifier")
        if self.get(identifier) is not None:
            raise ValueError(f"Web session already exists: {identifier}")
        session = WebSessionState(
            session_id=identifier,
            origin=normalized_origin,
            status=WebSessionStatus.ACTIVE,
            authentication_status=AuthenticationStatus.ANONYMOUS,
        )
        self.sessions.append(session)
        return session

    def ensure(self, session_id: str, origin: str) -> WebSessionState:
        session = self.get(session_id)
        if session is None:
            return self.create(origin, session_id=session_id)
        if session.origin != self._origin(origin):
            raise ValueError("Web session cannot cross its declared origin")
        if session.status in {WebSessionStatus.CLOSED, WebSessionStatus.EXPIRED}:
            raise ValueError("Web session is not active")
        return session

    def get(self, session_id: str) -> WebSessionState | None:
        return next((item for item in self.sessions if item.session_id == session_id), None)

    def request_state(self, session_id: str, url: str) -> tuple[dict[str, str], dict[str, str]]:
        session = self.ensure(session_id, url)
        return dict(session.headers), dict(session.cookies)

    def set_headers(self, session_id: str, headers: dict[str, str]) -> WebSessionState:
        session = self._active(session_id)
        blocked = {"cookie", "host", "content-length", "connection"}
        for name, value in headers.items():
            if name.lower() in blocked:
                raise ValueError(f"session header is managed by HTTPRequestTool: {name}")
            if re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", str(name)) is None:
                raise ValueError(f"invalid session header name: {name}")
            if any(ord(character) < 32 or ord(character) == 127
                   for character in f"{name}{value}"):
                raise ValueError("session headers must not contain control characters")
            session.headers[str(name)] = str(value)
        session.updated_at = utc_now_iso()
        return session

    def update_response(
        self,
        session_id: str,
        *,
        url: str,
        method: str,
        status_code: int | None,
        headers: Iterable[tuple[str, str]],
        response_cookies: dict[str, str],
        body: str,
    ) -> WebSessionState:
        session = self.ensure(session_id, url)
        session.cookies.update(response_cookies)
        header_items = list(headers)
        for name, value in header_items:
            if name.lower() in {"x-csrf-token", "x-xsrf-token"} and value:
                session.csrf_tokens[name] = value
        parser = _CsrfInputParser()
        parser.feed(body[:1_000_000])
        session.csrf_tokens.update(parser.tokens)
        path = urlsplit(url).path.lower()
        if status_code in {401, 403}:
            session.status = WebSessionStatus.ACTIVE
            session.authentication_status = AuthenticationStatus.CHALLENGED
        elif method.upper() == "POST" and re.search(r"/(?:login|signin|auth)(?:/|$)", path):
            if response_cookies and status_code is not None and status_code < 400:
                session.status = WebSessionStatus.AUTHENTICATED
                session.authentication_status = AuthenticationStatus.AUTHENTICATED
        elif session.status is WebSessionStatus.CREATED:
            session.status = WebSessionStatus.ACTIVE
        session.updated_at = utc_now_iso()
        return session

    def expire(self, session_id: str) -> WebSessionState:
        session = self._active(session_id)
        session.status = WebSessionStatus.EXPIRED
        session.authentication_status = AuthenticationStatus.EXPIRED
        session.updated_at = utc_now_iso()
        return session

    def close(self, session_id: str) -> WebSessionState:
        session = self._active(session_id)
        session.status = WebSessionStatus.CLOSED
        session.cookies.clear()
        session.headers.clear()
        session.csrf_tokens.clear()
        session.updated_at = utc_now_iso()
        return session

    def _active(self, session_id: str) -> WebSessionState:
        session = self.get(session_id)
        if session is None:
            raise ValueError(f"unknown Web session: {session_id}")
        if session.status in {WebSessionStatus.CLOSED, WebSessionStatus.EXPIRED}:
            raise ValueError("Web session is not active")
        return session

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlsplit(url)
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
