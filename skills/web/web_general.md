---
name: web_general
domain: web
description: Evidence-first orientation for authorized web CTF challenges.
tags: [web, http, request, response, php]
priority: HIGH
---

## Knowledge

- Treat routes, parameters, headers, cookies, and server behavior as separate evidence sources.
- Distinguish client-side restrictions from server-side authorization and validation.
- Preserve the relationship between an input variation and its observed response.

## Strategies

- Build a small map of reachable functionality before committing to one vulnerability class.
- Compare controlled variations and record only response differences that are reproducible.
- Promote a suspected weakness to a hypothesis until direct challenge evidence supports it.

## Heuristics

- Unexplained status, length, redirect, or privilege differences deserve a focused comparison.
- Error messages are evidence about parsing or data flow, not proof of exploitability.
