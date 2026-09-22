---
name: binary_analysis
domain: reverse
description: Form an evidence map for executable artifacts and their behavior.
tags: [binary, executable, mach-o, pe32, apk]
priority: HIGH
---

## Knowledge

- File format, architecture, imports, sections, and strings provide complementary clues.
- Compiler artifacts and library code should be separated from challenge-specific logic.
- Obfuscation changes confidence and cost but does not remove observable data flow.

## Strategies

- Establish the artifact's structure and likely entry paths before deep analysis.
- Link visible constants and messages to reachable control flow where evidence permits.
- Maintain explicit unknowns for packed, stripped, or malformed regions.

## Heuristics

- Validation messages and unusual constants are useful navigation anchors.
- Repeated decoding or comparison loops often delimit challenge-specific logic.
