---
name: classical_crypto
domain: crypto
description: Reason about substitution and transposition structures in CTF ciphertext.
tags: [caesar, vigenere, substitution, transposition, frequency]
priority: MEDIUM
---

## Knowledge

- Classical ciphers preserve different statistical and positional properties.
- Language, alphabet, spacing, and key-period assumptions strongly affect interpretation.
- A plausible fragment is weaker evidence than a consistent decode across the full message.

## Strategies

- Identify preserved structure before selecting a cipher family.
- Test key-length or shift hypotheses against multiple independent portions of text.
- Rank candidate plaintext by consistency with challenge context and format constraints.

## Heuristics

- Stable symbol frequencies support substitution reasoning more than short ciphertext does.
- Repeating patterns may indicate key periodicity or repeated plaintext structure.
