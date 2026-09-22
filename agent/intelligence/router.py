"""Deterministic R2 challenge classification and skill selection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Mapping

from agent.runtime.contracts import ChallengeSpec


@dataclass(frozen=True)
class SkillSelection:
    primary_skill: str
    secondary_skills: List[str] = field(default_factory=list)
    rationale: List[str] = field(default_factory=list)


class SkillRouter:
    """Use challenge text, metadata and artifact names without an LLM call."""

    RULES = {
        "web": ("http", "https", "url", "endpoint", "cookie", "session", "php", "sql", "xss", "sqli", "flask", "django"),
        "pwn": ("elf", "checksec", "amd64", "x86_64", "buffer overflow", "rop", "pwntools", "nc ", "netcat"),
        "reverse": ("ghidra", "ida", "disasm", "decompile", "apk", "assembly", "binary"),
        "crypto": ("rsa", "aes", "cipher", "modulus", "crypto", "hash", "ecdsa"),
        "forensics-disk": ("pcap", "disk", "image", "wireshark", "memory dump", "filesystem"),
        "misc": (),
    }

    def route(
        self,
        challenge: ChallengeSpec,
        artifacts: Iterable[str | Path | Mapping[str, object]] = (),
    ) -> SkillSelection:
        artifact_text = " ".join(self._artifact_text(item) for item in artifacts)
        category = (challenge.category or "").lower()
        text = " ".join([challenge.title, challenge.description, category, artifact_text]).lower()
        scores = {name: 0 for name in self.RULES}
        rationale: List[str] = []
        for skill, keywords in self.RULES.items():
            matches = [keyword for keyword in keywords if keyword in text]
            if matches:
                scores[skill] += len(matches)
                rationale.append(f"{skill}: {', '.join(matches)}")
            if category == skill or (skill == "forensics-disk" and category == "forensics"):
                scores[skill] += 3
                rationale.append(f"{skill}: challenge category")
        primary = max(scores, key=lambda skill: (scores[skill], skill != "misc"))
        if scores[primary] == 0:
            primary = "misc"
            rationale.append("misc: no deterministic domain signal")
        secondary = [
            skill
            for skill, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
            if skill != primary and skill != "misc" and score > 0
        ][:2]
        return SkillSelection(primary, secondary, rationale)

    @staticmethod
    def _artifact_text(item: str | Path | Mapping[str, object]) -> str:
        if isinstance(item, Mapping):
            return " ".join(str(value) for value in item.values())
        return str(item)
