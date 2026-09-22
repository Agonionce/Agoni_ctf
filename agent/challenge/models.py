"""Typed challenge intake models for R8.5."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Sequence
from urllib.parse import quote

from agent.challenge.validator import (
    reject_sensitive_name,
    reject_sensitive_text,
    require_text,
    slugify_name,
    validate_domain,
    validate_relative_workspace_path,
    validate_target_url,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_challenge_id(
    name: str,
    *,
    created_at: str,
    entropy: str | None = None,
) -> str:
    """Create ``<name>-<date>-<hash>`` without content-based workspace reuse."""

    reject_sensitive_name(name)
    slug = slugify_name(name)
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    digest_input = f"{slug}\0{created_at}\0{entropy or uuid.uuid4().hex}"
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:6]
    return f"{slug}-{created:%Y%m%d}-{digest}"


@dataclass(frozen=True)
class ChallengeManifest:
    """Portable description of one authorized challenge intake."""

    challenge_id: str
    name: str
    domain: str
    description: str
    target_url: str | None = None
    attachments: tuple[str, ...] = field(default_factory=tuple)
    source_paths: tuple[str, ...] = field(default_factory=tuple)
    authorization_scope: str = "authorized_ctf_only"
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        challenge_id = require_text(self.challenge_id, "challenge_id", max_length=160)
        if re.fullmatch(r"[A-Za-z0-9._-]+", challenge_id) is None:
            raise ValueError("challenge_id must be a normalized identifier")
        name = require_text(self.name, "name", max_length=200)
        description = require_text(self.description, "description")
        authorization_scope = require_text(
            self.authorization_scope,
            "authorization_scope",
            max_length=100,
        )
        created_at = require_text(self.created_at, "created_at", max_length=64)
        try:
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("created_at must be an ISO-8601 timestamp") from error
        reject_sensitive_name(name)
        reject_sensitive_text(description, "description")
        reject_sensitive_text(authorization_scope, "authorization_scope")
        object.__setattr__(self, "challenge_id", challenge_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "domain", validate_domain(self.domain))
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "target_url", validate_target_url(self.target_url))
        object.__setattr__(self, "authorization_scope", authorization_scope)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(
            self,
            "attachments",
            tuple(
                validate_relative_workspace_path(item, "attachments")
                for item in self.attachments
            ),
        )
        object.__setattr__(
            self,
            "source_paths",
            tuple(
                validate_relative_workspace_path(item, "source_paths")
                for item in self.source_paths
            ),
        )

    @classmethod
    def create(
        cls,
        *,
        name: str,
        domain: str,
        description: str,
        target_url: str | None = None,
        authorization_scope: str = "authorized_ctf_only",
        created_at: str | None = None,
        entropy: str | None = None,
    ) -> "ChallengeManifest":
        timestamp = created_at or utc_now_iso()
        return cls(
            challenge_id=new_challenge_id(
                name,
                created_at=timestamp,
                entropy=entropy,
            ),
            name=name,
            domain=domain,
            description=description,
            target_url=target_url,
            authorization_scope=authorization_scope,
            created_at=timestamp,
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["attachments"] = list(self.attachments)
        payload["source_paths"] = list(self.source_paths)
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChallengeManifest":
        return cls(
            challenge_id=str(data["challenge_id"]),
            name=str(data["name"]),
            domain=str(data["domain"]),
            description=str(data["description"]),
            target_url=(str(data["target_url"]) if data.get("target_url") else None),
            attachments=_string_tuple(data.get("attachments")),
            source_paths=_string_tuple(data.get("source_paths")),
            authorization_scope=str(
                data.get("authorization_scope", "authorized_ctf_only")
            ),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )

    def to_challenge_spec(self):
        """Build the existing Runtime contract without changing AgentRuntime."""

        from agent.runtime.contracts import ChallengeSpec

        attachment_uris = [_workspace_uri(item) for item in self.attachments]
        source_uris = [_workspace_uri(item) for item in self.source_paths]
        metadata: Dict[str, Any] = {
            "challenge_manifest": self.to_dict(),
            "attachment_paths": attachment_uris,
            "source_paths": source_uris,
            "legacy_attachment_paths": list(self.attachments),
            "legacy_source_paths": list(self.source_paths),
        }
        if self.target_url:
            metadata["base_url"] = self.target_url
            metadata["authorized_targets"] = [self.target_url]
        return ChallengeSpec(
            challenge_id=self.challenge_id,
            title=self.name,
            description=self.description,
            category=None if self.domain == "auto" else self.domain,
            authorization_scope=self.authorization_scope,
            metadata=metadata,
        )

    def to_question(self, *, experience_root: str | None = None):
        """Build the existing platform input contract for ``solve --challenge``."""

        from ctf_platform.base import Question

        attachment_uris = [_workspace_uri(item) for item in self.attachments]
        source_uris = [_workspace_uri(item) for item in self.source_paths]
        metadata: Dict[str, Any] = {
            "challenge_id": self.challenge_id,
            "category": None if self.domain == "auto" else self.domain,
            "authorization_scope": self.authorization_scope,
            "challenge_manifest": self.to_dict(),
            "attachment_paths": attachment_uris,
            "source_paths": source_uris,
            "legacy_attachment_paths": list(self.attachments),
            "legacy_source_paths": list(self.source_paths),
        }
        if experience_root:
            metadata["challenge_experience_root"] = experience_root
        if self.target_url:
            metadata["base_url"] = self.target_url
            metadata["authorized_targets"] = [self.target_url]
        return Question(
            title=self.name,
            content=self.description,
            attachments=attachment_uris,
            url=self.target_url,
            metadata=metadata,
        )


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("manifest path collections must be arrays")
    return tuple(str(item) for item in value)


def _workspace_uri(value: str) -> str:
    """Expose stored root-relative manifest paths through the R9.1 contract."""

    path = validate_relative_workspace_path(value, "workspace path")
    parts = path.split("/", 1)
    if parts[0] not in {"input", "work", "output"}:
        raise ValueError("manifest path must start with input, work, or output")
    suffix = f"/{quote(parts[1], safe='/-._~')}" if len(parts) == 2 else ""
    return f"workspace://{parts[0]}{suffix}"
