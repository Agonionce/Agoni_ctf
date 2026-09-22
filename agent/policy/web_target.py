"""Strict local-target validation shared by R5 policy and HTTP backend."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit


@dataclass(frozen=True)
class WebTargetValidation:
    allowed: bool
    reason: str
    parsed: SplitResult | None = None


def validate_local_web_target(url: str) -> WebTargetValidation:
    """Allow HTTP(S) loopback URLs only; reject public and ambiguous hosts."""

    if not isinstance(url, str) or not url.strip():
        return WebTargetValidation(False, "URL must be a non-empty string")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return WebTargetValidation(False, "URL has invalid host or port")
    if parsed.scheme not in {"http", "https"}:
        return WebTargetValidation(False, "only HTTP and HTTPS URLs are supported")
    if parsed.fragment:
        return WebTargetValidation(False, "URL fragments are not valid request targets")
    if not hostname or parsed.username is not None or parsed.password is not None:
        return WebTargetValidation(False, "URL must contain a host and no userinfo")
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost":
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)
            }
        except OSError:
            return WebTargetValidation(False, "localhost could not be resolved safely")
        if not addresses or not all(ipaddress.ip_address(item).is_loopback for item in addresses):
            return WebTargetValidation(False, "localhost resolved outside loopback")
        return WebTargetValidation(True, "loopback hostname", parsed)
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return WebTargetValidation(False, "R5 denies non-loopback hostnames")
    if not address.is_loopback:
        return WebTargetValidation(False, "R5 denies non-loopback addresses")
    return WebTargetValidation(True, "loopback address", parsed)


def web_origin(url: str) -> str | None:
    validation = validate_local_web_target(url)
    if not validation.allowed or validation.parsed is None:
        return None
    parsed = validation.parsed
    host = parsed.hostname
    if host is None:
        return None
    normalized = host.rstrip(".").lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{normalized}:{port}"


def is_scoped_local_web_target(url: str, authorized_targets: tuple[str, ...]) -> bool:
    candidate = web_origin(url)
    if candidate is None:
        return False
    return any(web_origin(target) == candidate for target in authorized_targets)
