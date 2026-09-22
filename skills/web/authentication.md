---
name: authentication
domain: web
description: Reason about identity, sessions, and authorization boundaries.
tags: [login, authentication, cookie, session, jwt]
priority: HIGH
---

## Knowledge

- Authentication establishes identity; authorization decides what that identity may access.
- Session state may be carried by cookies, tokens, hidden fields, or server-side records.
- A visible user identifier is not evidence that the server validates ownership.

## Strategies

- Model anonymous, ordinary, and privileged states separately.
- Compare how identity-bearing values are created, updated, and checked across transitions.
- Test one trust assumption at a time and retain the baseline response for comparison.

## Heuristics

- Client-controlled role or user identifiers are high-value trust-boundary hypotheses.
- A successful login does not imply protected endpoints enforce authorization consistently.
