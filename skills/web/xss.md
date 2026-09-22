---
name: xss
domain: web
description: Reason about untrusted data reaching browser execution contexts.
tags: [xss, javascript, html, browser, reflection]
priority: MEDIUM
---

## Knowledge

- Execution depends on the exact HTML, attribute, script, URL, or DOM context.
- Reflection, storage, and DOM transformation are different data-flow paths.
- Encoding that is safe in one browser context may be unsafe in another.

## Strategies

- Trace input from origin through server or client transformations to its final context.
- First prove controllable reflection or storage, then reason about context boundaries.
- Separate browser interpretation evidence from server-side response evidence.

## Heuristics

- Context changes around the same value often reveal incomplete output encoding.
- A reflected marker is useful evidence but is not by itself script execution.
