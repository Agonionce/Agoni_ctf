---
name: dynamic_analysis
domain: reverse
description: Plan bounded observations of runtime state for local authorized artifacts.
tags: [dynamic, runtime, trace, breakpoint, behavior]
priority: MEDIUM
---

## Knowledge

- Runtime observations can validate or reject static control-flow hypotheses.
- State at function boundaries is usually more interpretable than arbitrary snapshots.
- Anti-analysis behavior and environmental dependencies can distort observations.

## Strategies

- Choose observation points tied to a specific unanswered question.
- Compare state before and after one controlled input change.
- Feed confirmed runtime behavior back into the static evidence map.

## Heuristics

- Repeated comparison points are valuable for understanding validation state.
- Divergence between static expectation and runtime behavior should become an explicit finding.
