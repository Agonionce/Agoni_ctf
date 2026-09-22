"""Evidence-only Web technology detection from captured responses."""

from __future__ import annotations

import re
from typing import Iterable

from agent.domains.web.artifacts import ResponseArtifact, SessionArtifact
from agent.domains.web.intelligence.models import TechnologyEvidence


class TechnologyDetector:
    """Recognize bounded indicators; never infer a vulnerability."""

    HEADER_PATTERNS = {
        "nginx": re.compile(r"\bnginx\b", re.IGNORECASE),
        "Apache": re.compile(r"\bApache\b", re.IGNORECASE),
        "PHP": re.compile(r"\bPHP(?:/|\b)", re.IGNORECASE),
        "Flask": re.compile(r"\bFlask\b", re.IGNORECASE),
        "Werkzeug": re.compile(r"\bWerkzeug(?:/|\b)", re.IGNORECASE),
    }
    HTML_PATTERNS = {
        "Flask": re.compile(r"(?:generator[^>]+Flask|\bflask\b)", re.IGNORECASE),
        "PHP": re.compile(r"\.php(?:[?\"']|\b)", re.IGNORECASE),
        "SQLite": re.compile(r"\bSQLite\b", re.IGNORECASE),
        "WordPress": re.compile(r"(?:wp-content|WordPress)", re.IGNORECASE),
    }

    def detect(
        self,
        response: ResponseArtifact,
        session: SessionArtifact | None = None,
    ) -> list[TechnologyEvidence]:
        evidence: list[TechnologyEvidence] = []
        seen: set[tuple[str, str]] = set()
        for name, value in response.headers:
            if name.lower() not in {"server", "x-powered-by", "x-generator"}:
                continue
            for technology, pattern in self.HEADER_PATTERNS.items():
                if pattern.search(value):
                    self._append(
                        evidence,
                        seen,
                        technology,
                        f"{name} header contains {value[:200]}",
                        f"response {response.request_id} header",
                        "HIGH",
                    )
        body = response.body[:1_000_000]
        for technology, pattern in self.HTML_PATTERNS.items():
            if pattern.search(body):
                self._append(
                    evidence,
                    seen,
                    technology,
                    f"HTML contains a {technology} indicator",
                    f"response {response.request_id} HTML",
                    "MEDIUM",
                )
        if session is not None:
            names = {name.lower() for name in session.response_cookies}
            if "phpsessid" in names:
                self._append(
                    evidence,
                    seen,
                    "PHP",
                    "response sets a PHPSESSID cookie",
                    f"session {session.request_id}",
                    "HIGH",
                )
            if "session" in names:
                self._append(
                    evidence,
                    seen,
                    "Flask",
                    "response sets a generic session cookie used by Flask and other frameworks",
                    f"session {session.request_id}",
                    "LOW",
                )
        return evidence

    @staticmethod
    def technologies(evidence: Iterable[TechnologyEvidence]) -> list[str]:
        return sorted({item.technology for item in evidence})

    @staticmethod
    def _append(
        output: list[TechnologyEvidence],
        seen: set[tuple[str, str]],
        technology: str,
        evidence: str,
        source: str,
        confidence: str,
    ) -> None:
        identity = (technology, evidence)
        if identity in seen:
            return
        seen.add(identity)
        output.append(
            TechnologyEvidence(
                technology=technology,
                evidence=evidence,
                source=source,
                confidence=confidence,
            )
        )
