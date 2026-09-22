"""Build a same-origin Web attack surface from captured local evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable
from urllib.parse import parse_qsl, urljoin, urlsplit

from agent.domains.web.artifacts import RequestArtifact
from agent.domains.web.intelligence.models import HTMLAnalysis, WebAttackSurface
from agent.intelligence.models import Confidence, EndpointFinding


_CONFIDENCE_ORDER = {
    Confidence.LOW: 0,
    Confidence.MEDIUM: 1,
    Confidence.HIGH: 2,
    Confidence.CONFIRMED: 3,
}


class EndpointMapper:
    """Merge requests and passive HTML discoveries without probing endpoints."""

    def map(
        self,
        analyses: Iterable[HTMLAnalysis],
        requests: Iterable[RequestArtifact] = (),
        existing: Iterable[EndpointFinding] = (),
    ) -> WebAttackSurface:
        grouped: dict[tuple[str, str], dict[str, object]] = {}
        analysis_items = list(analyses)
        request_items = list(requests)
        base_url = (
            analysis_items[0].url
            if analysis_items
            else (request_items[0].url if request_items else "")
        )

        for item in existing:
            self._merge(
                grouped,
                item.path,
                item.method,
                item.parameters,
                item.source,
                item.confidence,
            )
        for request in request_items:
            path, query_parameters = self._same_origin_path(request.url, base_url)
            if path is not None:
                self._merge(
                    grouped,
                    path,
                    request.method,
                    [*query_parameters, *request.parameters],
                    f"request artifact {request.request_id}",
                    Confidence.CONFIRMED,
                )
        for analysis in analysis_items:
            if self._same_origin_path(analysis.url, base_url)[0] is None:
                continue
            for link in analysis.links:
                path, parameters = self._same_origin_path(link, analysis.url)
                if path is not None:
                    self._merge(
                        grouped,
                        path,
                        "GET",
                        parameters,
                        f"HTML link in {analysis.request_id}",
                        Confidence.MEDIUM,
                    )
            for form in analysis.forms:
                path, query_parameters = self._same_origin_path(form.action, analysis.url)
                if path is not None:
                    self._merge(
                        grouped,
                        path,
                        form.method,
                        [*query_parameters, *form.inputs],
                        f"HTML form in {analysis.request_id}",
                        Confidence.HIGH,
                    )
            for contract in analysis.client_requests:
                path, query_parameters = self._same_origin_path(
                    contract.path,
                    analysis.url,
                )
                if path is not None:
                    self._merge(
                        grouped,
                        path,
                        contract.method,
                        [
                            *query_parameters,
                            *(name for name, _value in contract.query),
                            *(name for name, _value in contract.json_body),
                        ],
                        contract.source,
                        Confidence.HIGH,
                    )
            for script in analysis.scripts:
                if script == "<inline>":
                    continue
                path, parameters = self._same_origin_path(script, analysis.url)
                if path is not None:
                    self._merge(
                        grouped,
                        path,
                        "GET",
                        parameters,
                        f"HTML script in {analysis.request_id}",
                        Confidence.MEDIUM,
                    )

        findings = [
            EndpointFinding(
                path=path,
                method=method,
                parameters=sorted(values["parameters"]),
                source=", ".join(sorted(values["sources"])),
                confidence=values["confidence"],
            )
            for (path, method), values in grouped.items()
        ]
        surface = WebAttackSurface(
            endpoints=findings,
            parameters=sorted(
                {
                    parameter
                    for finding in findings
                    for parameter in finding.parameters
                }
            ),
        )
        surface.normalize()
        return surface

    @staticmethod
    def _merge(
        grouped: dict[tuple[str, str], dict[str, object]],
        path: str,
        method: str,
        parameters: Iterable[str],
        source: str,
        confidence: Confidence,
    ) -> None:
        key = (path, method.upper())
        value = grouped.setdefault(
            key,
            {
                "parameters": set(),
                "sources": set(),
                "confidence": Confidence.LOW,
            },
        )
        parameter_set = value["parameters"]
        source_set = value["sources"]
        assert isinstance(parameter_set, set)
        assert isinstance(source_set, set)
        parameter_set.update(str(item) for item in parameters if str(item))
        source_set.add(source)
        current = value["confidence"]
        assert isinstance(current, Confidence)
        if _CONFIDENCE_ORDER[confidence] > _CONFIDENCE_ORDER[current]:
            value["confidence"] = confidence

    @staticmethod
    def _same_origin_path(
        target: str,
        base_url: str,
    ) -> tuple[str | None, list[str]]:
        if not target or target.startswith(("javascript:", "mailto:", "data:")):
            return None, []
        resolved = urlsplit(urljoin(base_url, target))
        base = urlsplit(base_url)
        if resolved.scheme not in {"http", "https"}:
            return None, []
        if (resolved.scheme, resolved.netloc) != (base.scheme, base.netloc):
            return None, []
        return resolved.path or "/", sorted(
            {name for name, _value in parse_qsl(resolved.query, keep_blank_values=True)}
        )
