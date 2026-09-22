---
name: memory_corruption
domain: pwn
description: Structure hypotheses about unsafe memory state transitions.
tags: [memory, heap, corruption, out-of-bounds, use-after-free]
priority: MEDIUM
---

## Knowledge

- Corruption requires a controllable violation of object, bounds, lifetime, or type assumptions.
- Crash location may be downstream from the first invalid state transition.
- Read, write, control-flow, and lifetime primitives have different evidentiary requirements.

## Strategies

- Minimize the triggering input and identify the earliest state divergence.
- Track attacker-controlled size, offset, pointer, and lifetime values independently.
- Separate a reliable primitive from assumptions about how it could later be used.

## Heuristics

- Reproducibility across small input changes is more useful than a single complex crash.
- Ownership and cleanup inconsistencies are strong lifetime-bug hypotheses.
