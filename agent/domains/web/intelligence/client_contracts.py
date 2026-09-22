"""Passive extraction of literal same-origin browser request contracts.

The extractor intentionally understands only static ``fetch()`` calls.  It
does not run JavaScript, resolve variables, make network calls, or turn a
contract into a Tool invocation.  Its job is to preserve useful evidence that
would otherwise be buried in a long HTML response.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable
from urllib.parse import parse_qsl, urljoin, urlsplit

from agent.domains.web.intelligence.models import ClientRequestContract


class ClientRequestContractAnalyzer:
    """Extract bounded literal ``fetch`` request shapes from client text."""

    MAX_CONTRACTS = 24
    MAX_SOURCE_CHARS = 100_000
    _FETCH = re.compile(
        r"\bfetch\s*\(\s*(?P<target>['\"](?:\\.|[^'\"\\]){1,2048}['\"])",
        re.IGNORECASE,
    )
    _METHOD = re.compile(r"\bmethod\s*:\s*['\"](?P<method>GET|POST)['\"]", re.IGNORECASE)
    _JSON_BODY = re.compile(
        r"\bbody\s*:\s*JSON\.stringify\s*\(\s*\{(?P<body>.{0,4096}?)\}\s*\)",
        re.IGNORECASE | re.DOTALL,
    )
    _HEADERS = re.compile(r"\bheaders\s*:\s*\{(?P<headers>.{0,2048}?)\}", re.IGNORECASE | re.DOTALL)
    _LITERAL_PAIR = re.compile(
        r"(?P<key>[A-Za-z_$][\w$]*|['\"](?:\\.|[^'\"\\]){1,256}['\"])\s*:\s*"
        r"(?P<value>['\"](?:\\.|[^'\"\\]){0,1024}['\"]|-?\d+(?:\.\d+)?|true|false|null)",
        re.IGNORECASE,
    )

    def analyze(
        self,
        sources: Iterable[str],
        base_url: str,
        *,
        source: str = "inline client code",
    ) -> tuple[ClientRequestContract, ...]:
        contracts: list[ClientRequestContract] = []
        seen: set[tuple[object, ...]] = set()
        for raw_source in sources:
            text = str(raw_source)[: self.MAX_SOURCE_CHARS]
            for match in self._FETCH.finditer(text):
                contract = self._contract_for(match, text, base_url, source)
                if contract is None:
                    continue
                identity = (
                    contract.method,
                    contract.path,
                    contract.query,
                    contract.json_body,
                    contract.header_names,
                )
                if identity in seen:
                    continue
                seen.add(identity)
                contracts.append(contract)
                if len(contracts) >= self.MAX_CONTRACTS:
                    return tuple(contracts)
        return tuple(contracts)

    def _contract_for(
        self,
        match: re.Match[str],
        text: str,
        base_url: str,
        source: str,
    ) -> ClientRequestContract | None:
        target = self._literal(match.group("target"))
        if target is None:
            return None
        resolved = urlsplit(urljoin(base_url, target))
        base = urlsplit(base_url)
        if (
            resolved.scheme not in {"http", "https"}
            or (resolved.scheme, resolved.netloc) != (base.scheme, base.netloc)
        ):
            return None
        # This bounded suffix spans the ordinary options object but never
        # attempts to parse arbitrary JavaScript or evaluate expressions.
        suffix = text[match.end() : match.end() + 8_000]
        method_match = self._METHOD.search(suffix)
        method = method_match.group("method").upper() if method_match else "GET"
        body_match = self._JSON_BODY.search(suffix)
        headers_match = self._HEADERS.search(suffix)
        return ClientRequestContract(
            method=method,
            path=resolved.path or "/",
            query=tuple(parse_qsl(resolved.query, keep_blank_values=True)),
            json_body=self._pairs(body_match.group("body")) if body_match else (),
            header_names=tuple(
                name for name, _value in self._pairs(headers_match.group("headers"))
            ) if headers_match else (),
            source=source,
        )

    @classmethod
    def _pairs(cls, value: str) -> tuple[tuple[str, str], ...]:
        pairs: list[tuple[str, str]] = []
        for match in cls._LITERAL_PAIR.finditer(value):
            raw_key = match.group("key")
            key = (
                cls._literal(raw_key)
                if raw_key[:1] in {"'", '\"'}
                else raw_key
            )
            item = cls._literal(match.group("value"))
            if key is None or item is None:
                continue
            pairs.append((key, item))
        return tuple(dict.fromkeys(pairs))

    @staticmethod
    def _literal(value: str) -> str | None:
        try:
            if value[:1] in {"'", '\"'}:
                parsed = ast.literal_eval(value)
                return parsed if isinstance(parsed, str) else None
        except (SyntaxError, ValueError):
            return None
        if value.lower() in {"true", "false", "null"} or re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            return value
        return None
