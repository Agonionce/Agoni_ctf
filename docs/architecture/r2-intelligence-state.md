# Agonionce R2 — CTF Intelligence State & Persistent Reasoning

R2 adds durable, structured CTF knowledge. It is not chat-history compression,
RAG, an embedding system, a vector database, a web runtime, or a multi-agent
system.

## State path

```text
Observation
  ↓
AnalysisResult + KnowledgeUpdateSuggestion
  ↓
KnowledgeUpdater
  ↓
IntelligenceStore / IntelligenceState
  ↓
IntelligenceRetriever
  ↓
Planner Context
```

The Analyzer never writes state directly. It can only return typed suggestions;
`KnowledgeUpdater` validates and applies them after each observation. Facts and
hypotheses are separate by model and prompt contract.

## State models

- `Fact`: confirmed information, confidence, source step, evidence artifacts.
- `Hypothesis`: an unverified statement with an explicit lifecycle.
- `FailedAttempt`: method, target, input, result, reason, step, artifacts.
- `Finding`: important interpretation linked to facts and artifacts.
- `Credential`: CTF-discovered credential material; safe views mask its value.
- `AttackSurface`: extensible target-entry record.
- `OpenQuestion`: unresolved, answered, or discarded investigation question.
- `ArtifactReference` / `ArtifactLink`: relations back to R1 artifacts.

`IntelligenceStore` is the only CRUD entry point. It supports in-memory state,
atomic JSON save/load, category/keyword queries, state summaries, and artifact
relations. It intentionally has no vector index or external database.

## Retrieval and skills

`IntelligenceRetriever` selects a bounded Planner view using keyword overlap,
optional categories, and high-importance/confirmed-item preference. It does
not serialize the full state into every prompt. Credential values are masked in
retrieved context.

R2 introduced a small deterministic `SkillRouter` for challenge classification.
R3 supersedes that compatibility classifier with the separate Domain contract,
validated skill assets, R3 `SkillRouter`, and bounded domain context builder.
The R2 state and retrieval contracts remain unchanged.

## Checkpoint V2 and resume

`IntelligenceCheckpoint` persists one R2 snapshot directory:

```text
checkpoints/r2_<run-id>/
├── run.json
├── intelligence.json
└── artifacts.json
```

Load reconstructs typed `RunState`, `IntelligenceStore`, and artifact metadata.
The normal Workflow can offer the latest snapshot for resume. R4 extends new
snapshots with an optional `domain_runtime.json`; the original three-file R2
format remains loadable. A checkpoint for another challenge is rejected before
runtime construction.

R6 adds `experiments.json` to new snapshots. It contains hypotheses,
experiments, and evidence as a dedicated experiment-loop view. Restore checks
that this view is consistent with `intelligence.json`; older R2/R4/R5 snapshots
without it remain loadable.

## Security and limits

Credential material may be retained only when discovered in authorized CTF or
local-lab evidence. CLI and retrieval views mask it; no API configuration is
read into IntelligenceState. Checkpoint files are local JSON and are ignored by
Git through the existing `checkpoints/` rule.

R2 is still not an OS sandbox or a web/pwn/reverse execution runtime. R1 tool
policy remains the boundary for any execution performed in future work.
