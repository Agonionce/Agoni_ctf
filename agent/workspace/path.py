"""Canonical workspace URI parsing and containment enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import quote, unquote, urlsplit


WORKSPACE_SCHEME = "workspace"
PUBLIC_WORKSPACE_SCOPES = ("input", "work", "output")
_INTERNAL_WORKSPACE_SCOPES = (*PUBLIC_WORKSPACE_SCOPES, "logs")


@dataclass(frozen=True)
class ResolvedWorkspacePath:
    """A contained host path paired with its canonical workspace identity."""

    uri: str
    scope: str
    path: Path
    relative_path: str


class WorkspacePathResolver:
    """Resolve canonical workspace URIs without exposing host path semantics.

    ``workspace://input/...``, ``workspace://work/...`` and
    ``workspace://output/...`` are the public contract. Root-relative legacy
    values such as ``input/source/app.py`` and work-relative values such as
    ``solve.py`` remain accepted at this compatibility boundary only.
    """

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        scope_roots: Mapping[str, str | Path] | None = None,
    ) -> None:
        root = Path(workspace_root).resolve()
        default_roots: dict[str, Path] = {
            "input": root / "input",
            "work": root / "work",
            "output": root / "output",
            "logs": root / "logs",
        }
        if scope_roots is not None:
            for name, value in scope_roots.items():
                if name not in _INTERNAL_WORKSPACE_SCOPES:
                    raise ValueError(f"unknown workspace scope: {name}")
                default_roots[name] = Path(value)
        self.workspace_root = root
        self.scope_roots = {
            name: self._contained(Path(value).resolve(), root)
            for name, value in default_roots.items()
        }

    def resolve(
        self,
        value: str | Path,
        *,
        allowed_scopes: Iterable[str] = PUBLIC_WORKSPACE_SCOPES,
        default_scope: str = "work",
    ) -> ResolvedWorkspacePath:
        """Resolve one path and enforce both containment and scope access."""

        raw_value = str(value)
        if not raw_value or "\x00" in raw_value or "\\" in raw_value:
            raise ValueError("workspace path must be a non-empty portable path")
        allowed = frozenset(allowed_scopes)
        if not allowed or any(scope not in self.scope_roots for scope in allowed):
            raise ValueError("allowed workspace scopes are invalid")

        if raw_value.startswith(f"{WORKSPACE_SCHEME}://"):
            scope, relative = self._parse_uri(raw_value)
        else:
            scope, relative = self._parse_legacy(raw_value, default_scope)
        if scope not in allowed:
            raise ValueError(f"workspace scope is not allowed: {scope}")

        scope_root = self.scope_roots[scope]
        resolved = (scope_root / relative).resolve()
        self._contained(resolved, scope_root)
        relative_text = resolved.relative_to(scope_root).as_posix()
        uri = self._format_uri(scope, relative_text)
        return ResolvedWorkspacePath(uri, scope, resolved, relative_text)

    def to_uri(
        self,
        value: str | Path,
        *,
        allowed_scopes: Iterable[str] = PUBLIC_WORKSPACE_SCOPES,
        default_scope: str = "work",
    ) -> str:
        return self.resolve(
            value,
            allowed_scopes=allowed_scopes,
            default_scope=default_scope,
        ).uri

    def uri_for_path(
        self,
        value: str | Path,
        *,
        allowed_scopes: Iterable[str] = PUBLIC_WORKSPACE_SCOPES,
    ) -> str:
        """Convert an already resolved host path to a canonical workspace URI."""

        resolved = Path(value).resolve()
        for scope in allowed_scopes:
            scope_root = self.scope_roots.get(scope)
            if scope_root is None:
                continue
            try:
                relative = resolved.relative_to(scope_root).as_posix()
            except ValueError:
                continue
            return self._format_uri(scope, relative)
        raise ValueError("path is outside the allowed workspace scopes")

    @staticmethod
    def _parse_uri(value: str) -> tuple[str, Path]:
        parsed = urlsplit(value)
        if (
            parsed.scheme != WORKSPACE_SCHEME
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            raise ValueError("invalid workspace URI")
        scope = parsed.hostname or ""
        decoded = unquote(parsed.path).lstrip("/")
        if "\\" in decoded or "\x00" in decoded:
            raise ValueError("workspace URI contains a non-portable path")
        relative = Path(decoded or ".")
        WorkspacePathResolver._validate_relative(relative)
        return scope, relative

    def _parse_legacy(self, value: str, default_scope: str) -> tuple[str, Path]:
        raw = Path(value)
        if raw.is_absolute():
            resolved = raw.resolve()
            for scope, root in self.scope_roots.items():
                try:
                    relative = resolved.relative_to(root)
                except ValueError:
                    continue
                self._validate_relative(relative)
                return scope, relative
            raise ValueError("path escapes challenge workspace")
        self._validate_relative(raw)
        parts = raw.parts
        if parts and parts[0] in self.scope_roots:
            return parts[0], Path(*parts[1:]) if len(parts) > 1 else Path(".")
        if default_scope not in self.scope_roots:
            raise ValueError(f"unknown default workspace scope: {default_scope}")
        return default_scope, raw

    @staticmethod
    def _validate_relative(path: Path) -> None:
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            if path == Path("."):
                return
            raise ValueError("workspace path traversal is not allowed")

    @staticmethod
    def _format_uri(scope: str, relative: str) -> str:
        encoded = quote(relative, safe="/-._~")
        suffix = "" if relative in {"", "."} else f"/{encoded}"
        return f"{WORKSPACE_SCHEME}://{scope}{suffix}"

    @staticmethod
    def _contained(path: Path, root: Path) -> Path:
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ValueError("path escapes challenge workspace") from error
        return path
