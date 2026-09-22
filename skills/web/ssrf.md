---
name: ssrf
domain: web
description: Analyze server-side resource-fetch behavior within authorized targets.
tags: [ssrf, url, fetch, callback, internal]
priority: MEDIUM
---

## Knowledge

- SSRF requires evidence that the server, rather than the client, initiates a request.
- URL parsing, redirects, allowlists, and destination resolution form separate controls.
- Blind behavior may expose only timing or secondary application effects.

## Strategies

- Identify features that ingest locations or resource references and map their validation path.
- Distinguish parser acceptance from a confirmed server-side fetch.
- Keep target reasoning inside the challenge's explicit authorization scope.

## Heuristics

- Image importers, callbacks, previews, and URL validators are common server-fetch surfaces.
- Differences after redirects may indicate validation and fetching occur at different stages.
