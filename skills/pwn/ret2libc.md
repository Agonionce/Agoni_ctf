---
name: ret2libc
domain: pwn
description: Reason about return-to-library prerequisites without assuming an exploit primitive.
tags: [ret2libc, libc, return-to-libc, leak, rop]
priority: MEDIUM
---

## Knowledge

- A return-to-library path requires control flow, calling-convention alignment, and address knowledge.
- Library identity and base-address evidence are separate prerequisites.
- Partial leaks may be ambiguous across library versions or process layouts.

## Strategies

- Track control, leak, library identity, and argument setup as independent prerequisites.
- Prefer evidence-backed addresses and state assumptions explicitly.
- Reassess feasibility when any prerequisite remains unresolved.

## Heuristics

- A linked library symbol is not proof that its runtime address is known.
- Reliable disclosure often matters before constructing a return-oriented path.
