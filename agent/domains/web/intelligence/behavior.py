"""Response comparison that reports evidence rather than vulnerability verdicts."""

from __future__ import annotations

import hashlib
import re

from agent.domains.web.artifacts import ResponseArtifact
from agent.domains.web.intelligence.html_analyzer import HTMLAnalyzer
from agent.domains.web.intelligence.models import (
    BehaviorFinding,
    ResponseDifference,
)


class ResponseBehaviorAnalyzer:
    ERROR_PATTERNS = {
        "sql syntax error": re.compile(r"sql\s+syntax|syntax\s+error.*sql", re.I),
        "database error": re.compile(r"database\s+error|db\s+error", re.I),
        "sqlite error": re.compile(r"sqlite(?:3)?(?:\.|\s+).*?(?:error|exception)", re.I),
        "exception traceback": re.compile(r"traceback\s*\(most recent call last\)", re.I),
        "unhandled exception": re.compile(r"unhandled\s+exception", re.I),
    }
    DATABASE_SIGNALS = frozenset(
        {"sql syntax error", "database error", "sqlite error"}
    )

    def compare(
        self,
        baseline: ResponseArtifact,
        current: ResponseArtifact,
    ) -> tuple[ResponseDifference, list[BehaviorFinding]]:
        baseline_title = HTMLAnalyzer().analyze(baseline).title
        current_title = HTMLAnalyzer().analyze(current).title
        baseline_errors = self.detect_errors(baseline.body)
        current_errors = self.detect_errors(current.body)
        difference = ResponseDifference(
            baseline_request_id=baseline.request_id,
            current_request_id=current.request_id,
            status_changed=baseline.status_code != current.status_code,
            baseline_status=baseline.status_code,
            current_status=current.status_code,
            length_difference=len(current.body) - len(baseline.body),
            title_changed=baseline_title != current_title,
            baseline_title=baseline_title,
            current_title=current_title,
            baseline_errors=tuple(baseline_errors),
            current_errors=tuple(current_errors),
            content_changed=self._digest(baseline.body) != self._digest(current.body),
        )
        findings: list[BehaviorFinding] = []
        database_errors = (set(baseline_errors) | set(current_errors)) & self.DATABASE_SIGNALS
        if database_errors and (
            set(baseline_errors) != set(current_errors) or difference.content_changed
        ):
            findings.append(
                BehaviorFinding(
                    title="Possible database-related behavior",
                    description=(
                        "Captured responses differ and contain database-related error "
                        "signals. This is evidence for a bounded experiment, not "
                        "confirmation of SQL injection."
                    ),
                    response_ids=(baseline.request_id, current.request_id),
                )
            )
        return difference, findings

    def detect_errors(self, body: str) -> list[str]:
        return sorted(
            name for name, pattern in self.ERROR_PATTERNS.items() if pattern.search(body)
        )

    @staticmethod
    def _digest(body: str) -> str:
        return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
