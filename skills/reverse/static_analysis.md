---
name: static_analysis
domain: reverse
description: Derive control-flow and data-flow hypotheses without executing the artifact.
tags: [static, decompile, disassembly, strings, control-flow]
priority: MEDIUM
---

## Knowledge

- Decompiled output is an approximation and must be reconciled with lower-level behavior.
- Function boundaries, types, and names may be incomplete or misleading.
- Constants, cross-references, and call relationships can connect input to validation logic.

## Strategies

- Start from observable inputs or outputs and trace toward decision points.
- Rename concepts by behavior and evidence rather than guessed intent.
- Convert complex checks into small, independently testable logical statements.

## Heuristics

- Suspiciously simple decompiler output may hide optimized or misidentified operations.
- A branch controlling success output is a strong backward-slicing anchor.
