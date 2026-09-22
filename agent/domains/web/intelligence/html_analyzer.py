"""Deterministic HTML structure extraction with no JavaScript execution."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlsplit

from agent.domains.web.artifacts import ResponseArtifact
from agent.domains.web.intelligence.client_contracts import ClientRequestContractAnalyzer
from agent.domains.web.intelligence.models import HTMLAnalysis, HTMLForm


class _StructureParser(HTMLParser):
    def __init__(self, default_action: str) -> None:
        super().__init__(convert_charrefs=True)
        self.default_action = default_action
        self.forms: list[dict[str, object]] = []
        self._current_form: dict[str, object] | None = None
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.comments: list[str] = []
        self.inline_scripts: list[str] = []
        self.event_handlers: list[str] = []
        self._inline_script_parts: list[str] | None = None
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {name.lower(): value for name, value in attrs}
        lowered = tag.lower()
        self.event_handlers.extend(
            str(value)[:10_000]
            for name, value in attributes.items()
            if name.startswith("on") and value
        )
        if lowered == "form":
            self._current_form = {
                "action": attributes.get("action") or self.default_action,
                "method": str(attributes.get("method") or "GET").upper(),
                "inputs": [],
            }
            self.forms.append(self._current_form)
        elif lowered in {"input", "select", "textarea", "button"}:
            name = attributes.get("name")
            if self._current_form is not None and name:
                inputs = self._current_form["inputs"]
                assert isinstance(inputs, list)
                if name not in inputs:
                    inputs.append(name)
        elif lowered == "a" and attributes.get("href"):
            self.links.append(str(attributes["href"]))
        elif lowered == "script":
            self.scripts.append(str(attributes.get("src") or "<inline>"))
            if not attributes.get("src"):
                self._inline_script_parts = []
        elif lowered == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "form":
            self._current_form = None
        elif lowered == "title":
            self._in_title = False
        elif lowered == "script" and self._inline_script_parts is not None:
            source = "".join(self._inline_script_parts).strip()
            if source:
                self.inline_scripts.append(source[:100_000])
            self._inline_script_parts = None

    def handle_data(self, data: str) -> None:
        if self._inline_script_parts is not None:
            self._inline_script_parts.append(data)
        if self._in_title and data.strip():
            self._title_parts.append(data.strip())

    def handle_comment(self, data: str) -> None:
        comment = " ".join(data.split())
        if comment:
            self.comments.append(comment[:500])

    @property
    def title(self) -> str | None:
        title = " ".join(self._title_parts).strip()
        return title[:500] if title else None


class HTMLAnalyzer:
    """Extract static HTML structure and literal browser request shapes only."""

    def analyze(self, response: ResponseArtifact) -> HTMLAnalysis:
        default_path = urlsplit(response.url).path or "/"
        parser = _StructureParser(default_path)
        parser.feed(response.body)
        parser.close()
        forms = tuple(
            HTMLForm(
                action=str(item["action"]),
                method=str(item["method"]),
                inputs=tuple(sorted(str(name) for name in item["inputs"])),
            )
            for item in parser.forms
        )
        client_requests = ClientRequestContractAnalyzer().analyze(
            [*parser.inline_scripts, *parser.event_handlers],
            response.url,
            source=f"inline client code in {response.request_id}",
        )
        return HTMLAnalysis(
            request_id=response.request_id,
            url=response.url,
            title=parser.title,
            forms=forms,
            links=tuple(dict.fromkeys(parser.links)),
            scripts=tuple(dict.fromkeys(parser.scripts)),
            comments=tuple(dict.fromkeys(parser.comments)),
            client_requests=client_requests,
        )
