---
name: hash_analysis
domain: crypto
description: Classify digest evidence and evaluate challenge-specific recovery hypotheses.
tags: [hash, digest, md5, sha1, sha256]
priority: MEDIUM
---

## Knowledge

- Digest length and alphabet narrow candidates but do not uniquely identify an algorithm.
- Hashing, keyed authentication, and password storage have different inputs and threat models.
- Recovery feasibility depends on the challenge's candidate space and constraints.

## Strategies

- Record format, length, surrounding fields, and any known input relationship.
- Derive candidate-space constraints from challenge evidence before considering enumeration.
- Validate candidates by exact reproduction rather than visual resemblance.

## Heuristics

- Common digest lengths are classification clues, not confirmation.
- Salts, prefixes, and composition rules can matter more than the named hash primitive.
