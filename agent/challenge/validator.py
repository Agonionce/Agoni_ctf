"""Validation and security rules for the R8.5 Challenge Intake Layer."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit


class ChallengeValidationError(ValueError):
    """Raised when challenge intake data violates its typed contract."""


class ChallengeSecurityError(ChallengeValidationError):
    """Raised when challenge intake could expose sensitive local data."""


ALLOWED_DOMAINS = frozenset({"auto", "web", "pwn", "reverse", "crypto", "misc"})
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(
        r"(?i)\b(?:flag|ctf|htb|[A-Za-z0-9_-]{1,24}ctf)\{[^}\r\n]+\}"
    ),
    re.compile(r"(?i)\bsk-[a-z0-9_-]{8,}"),
    re.compile(
        r"(?i)\b(?:authorization|proxy-authorization|x-api-key|api[_-]?key|"
        r"password|passwd|token|cookie|set-cookie|secret|credential|x-session)"
        r"\s*(?::|=|\bis\b)\s*[^\s<>{}\[\]]+"
    ),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{6,}"),
)
_SENSITIVE_FILE_NAMES = frozenset(
    {
        ".env",
        ".npmrc",
        ".pypirc",
        "config.json",
        "credentials",
        "credentials.json",
        "id_ed25519",
        "id_rsa",
    }
)
_GENERIC_FLAG_VALUE_PATTERN = re.compile(
    r"(?i)\b[A-Za-z][A-Za-z0-9_-]{1,31}\{[^}\r\n]+\}"
)


def slugify_name(value: str) -> str:
    """Return a stable filesystem-safe key without restricting display names."""

    normalized = normalize_challenge_name(value)
    ascii_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip(".-_").lower()
    has_non_ascii = any(ord(character) > 127 for character in normalized)
    if has_non_ascii:
        digest = hashlib.sha256(normalized.casefold().encode("utf-8")).hexdigest()[:8]
        prefix = ascii_slug[:100].rstrip(".-_") or "challenge"
        return f"{prefix}-{digest}"
    if not ascii_slug:
        raise ChallengeValidationError("challenge name must contain visible text")
    return ascii_slug[:120].rstrip(".-_")


def normalize_challenge_name(value: object) -> str:
    """Normalize a user-facing name for equality while preserving Unicode."""

    name = require_text(value, "name", max_length=200)
    compatible = unicodedata.normalize("NFKC", name)
    return re.sub(r"\s+", " ", compatible).strip()


def challenge_name_key(value: object) -> str:
    """Return a case-insensitive Unicode key used only for duplicate checks."""

    return normalize_challenge_name(value).casefold()


def require_text(
    value: object,
    field_name: str,
    *,
    max_length: int = 100_000,
) -> str:
    if not isinstance(value, str):
        raise ChallengeValidationError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ChallengeValidationError(f"{field_name} must be a non-empty string")
    if len(normalized) > max_length:
        raise ChallengeValidationError(f"{field_name} exceeds the intake size limit")
    return normalized


def reject_sensitive_text(value: str, field_name: str) -> None:
    """Reject concrete secrets while allowing ordinary security terminology."""

    for pattern in _SENSITIVE_TEXT_PATTERNS:
        if pattern.search(value):
            raise ChallengeSecurityError(f"{field_name} contains sensitive data")


def reject_sensitive_name(value: str) -> None:
    """Reject any flag-shaped display name before it can influence a public ID."""

    reject_sensitive_text(value, "name")
    if _GENERIC_FLAG_VALUE_PATTERN.search(value):
        raise ChallengeSecurityError("name contains sensitive data")


def validate_domain(value: object) -> str:
    domain = require_text(value, "domain", max_length=32).lower()
    if domain not in ALLOWED_DOMAINS:
        raise ChallengeValidationError(
            f"domain must be one of: {', '.join(sorted(ALLOWED_DOMAINS))}"
        )
    return domain


def validate_target_url(value: object | None) -> str | None:
    if value is None or value == "":
        return None
    target_url = require_text(value, "target_url", max_length=2048)
    parsed = urlsplit(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ChallengeValidationError("target_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ChallengeSecurityError("target_url must not contain credentials")
    reject_sensitive_text(target_url, "target_url")
    return target_url


def validate_relative_workspace_path(value: object, field_name: str) -> str:
    path_text = require_text(value, field_name, max_length=4096)
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise ChallengeValidationError(
            f"{field_name} must remain relative to the challenge workspace"
        )
    return path.as_posix()


def reject_sensitive_path(path: Path) -> None:
    """Reject common credential/configuration files before any copy occurs."""

    lowered = path.name.lower()
    if (
        lowered in _SENSITIVE_FILE_NAMES
        or lowered.startswith(".env.")
        or lowered.endswith(".pem")
        or lowered.endswith(".key")
    ):
        raise ChallengeSecurityError(f"refusing to import sensitive file: {path.name}")
