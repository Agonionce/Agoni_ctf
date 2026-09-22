---
name: binary_triage
domain: pwn
description: Establish architecture, mitigations, interfaces, and evidence for a binary challenge.
tags: [elf, binary, amd64, i386, canary, pie, nx]
priority: HIGH
---

## Knowledge

- Architecture, linkage, mitigations, and input boundaries constrain later exploit reasoning.
- Imported functions and visible messages suggest behavior but do not prove reachability.
- Local and remote challenge environments may differ in libraries and observable behavior.

## Strategies

- Record format, architecture, protections, and expected interaction before choosing a flaw class.
- Map input paths to parsing and memory operations using reproducible evidence.
- Keep environmental assumptions explicit and downgrade confidence when artifacts are missing.

## Heuristics

- Unknown binary properties should trigger triage, not an immediate exploit hypothesis.
- Mitigations change strategy priority but do not establish whether a vulnerability exists.
