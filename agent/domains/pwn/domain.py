"""Pwn challenge knowledge classification only; no exploit runtime."""

from agent.domains.base import RuleDomain


class PwnDomain(RuleDomain):
    def __init__(self) -> None:
        super().__init__(
            name="pwn",
            description="Reasoning patterns for authorized binary exploitation challenges.",
            skill_names=("binary_triage", "memory_corruption", "stack_overflow", "ret2libc"),
            signals=(
                "pwn", "elf", "amd64", "x86_64", "i386", "binary", "libc", "nc",
                "heap", "stack", "canary", "pie", "nx", "rop",
            ),
            skill_signals={
                "binary_triage": ("elf", "amd64", "i386", "binary", "canary", "pie", "nx"),
                "memory_corruption": ("memory corruption", "heap", "use-after-free", "out-of-bounds"),
                "stack_overflow": ("stack overflow", "buffer overflow", "stack", "canary"),
                "ret2libc": ("ret2libc", "libc", "return-to-libc"),
            },
        )
