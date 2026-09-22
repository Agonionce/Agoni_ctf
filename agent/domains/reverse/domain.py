"""Reverse challenge knowledge classification only; no decompiler runtime."""

from agent.domains.base import RuleDomain


class ReverseDomain(RuleDomain):
    def __init__(self) -> None:
        super().__init__(
            name="reverse",
            description="Reasoning patterns for authorized reverse-engineering challenges.",
            skill_names=("binary_analysis", "static_analysis", "dynamic_analysis"),
            signals=(
                "reverse", "reversing", "decompile", "disassembly", "assembly", "opcode",
                "apk", "mach-o", "pe32", "packed", "obfuscated",
            ),
            skill_signals={
                "binary_analysis": ("binary", "executable", "mach-o", "pe32", "apk"),
                "static_analysis": ("static", "decompile", "disassembly", "strings", "control flow"),
                "dynamic_analysis": ("dynamic", "runtime behavior", "trace", "breakpoint"),
            },
        )
