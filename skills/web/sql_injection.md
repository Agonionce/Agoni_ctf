---
name: sql_injection
domain: web
description: Identify and validate SQL data-flow hypotheses from controlled evidence.
tags: [sql, sqli, database, query, mysql, sqlite]
priority: HIGH
---

## Knowledge

- SQL injection is a server-side data-flow flaw; surface errors alone are not confirmation.
- Input context, query shape, backend behavior, and response channel constrain viable hypotheses.
- Boolean, error, timing, and returned-data effects are distinct evidence channels.

## Strategies

- Establish a stable baseline, then vary one syntactic or logical property at a time.
- Infer likely input context from paired outcomes before considering extraction paths.
- Record rejected payload families and filtering evidence to avoid repeating failed approaches.

## Heuristics

- Reproducible true-versus-false response differences are stronger than one-off server errors.
- Authentication and search parameters commonly expose query construction boundaries.
