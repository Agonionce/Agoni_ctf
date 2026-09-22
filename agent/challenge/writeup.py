"""Deterministic R8.5 writeup scaffolding; no LLM generation is performed."""

from __future__ import annotations


class WriteupTemplate:
    """Render the stable challenge writeup skeleton required by the pipeline."""

    @staticmethod
    def render(challenge_name: str) -> str:
        return (
            f"# {challenge_name}\n\n"
            "## Overview\n\n"
            "## Recon\n\n"
            "## Analysis\n\n"
            "## Experiments\n\n"
            "## Evidence\n\n"
            "## Solution\n\n"
            "## Flag\n\n"
            "## Lessons Learned\n"
        )
