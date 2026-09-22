---
name: encoding
domain: crypto
description: Identify reversible representation layers before assuming encryption.
tags: [encoding, base64, base32, hex, ascii]
priority: HIGH
---

## Knowledge

- Encoding changes representation without requiring a secret key.
- Alphabet, padding, length, and character distribution constrain plausible formats.
- Multiple representation layers may be nested with text or binary boundaries between them.

## Strategies

- Classify visible structure and test the simplest reversible interpretation first.
- Preserve raw bytes and record each transformation as a separate evidence step.
- Stop layering transformations when output structure becomes less plausible.

## Heuristics

- Restricted alphabets and regular length boundaries strongly suggest an encoding family.
- Human-readable intermediate output is useful but still requires challenge-context validation.
