---
name: stack_overflow
domain: pwn
description: Analyze evidence for stack-bound overwrite conditions and constraints.
tags: [stack, overflow, buffer, canary]
priority: HIGH
---

## Knowledge

- Input length, destination capacity, and copy semantics determine overwrite potential.
- A crash does not establish control over saved state or bypass of stack protections.
- Offset stability depends on architecture, call path, and input transformations.

## Strategies

- Determine the smallest length transition that changes behavior.
- Identify which adjacent values are influenced before reasoning about control flow.
- Record bad characters, truncation, and protection evidence as explicit constraints.

## Heuristics

- Length-dependent failures near fixed boundaries support a bounded-overwrite hypothesis.
- Stack protection evidence should shift the investigation toward leak or logic prerequisites.
