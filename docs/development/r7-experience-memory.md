# Agonionce R7 Completion Report

## Architecture

R7 adds a global Experience Layer for deterministic reuse of generic lessons
across challenges:

```text
Completed Run
  |
  v
Experience Extractor
  |
  v
Experience Record
  |
  v
Experience Store
  |
  v
Experience Retriever
  |
  v
Planner Context
```

Experience remains separate from current-challenge intelligence:

```text
IntelligenceState = what is known about this challenge
ExperienceStore    = what generic pattern was useful in a past run
```

The layer is implemented under `agent/experience/`. It has no Tool, network,
LLM, model-training, Skill-writing, graph, vector, or multi-agent capability.

## Models

`ExperienceRecord` stores:

- `id`
- `domain`
- `category`
- `trigger`
- `pattern`
- `strategy`
- `lesson`
- `failure`
- `source_run`
- `confidence`
- `created_at`

Identifiers and confidence are validated. Reusable text is size-bounded and
rejects target-specific URL/IP data, flag-shaped answers, API-key patterns, and
credential/secret assignments. Records contain generic guidance, not copied
observations or challenge solutions.

## Extractor

`ExperienceExtractor` accepts a completed `RunState`, its
`IntelligenceState`, experiment history, and evidence. The first implementation
is fully rule-driven and makes no LLM call.

Rules currently recognize reusable foundations for:

- `sql_injection`
- `authentication`
- `binary_analysis`
- `crypto_pattern`

Source challenge, hypothesis, experiment, and evidence text is used only for
local rule matching. Output text comes from generic templates, so credentials,
flags, payloads, endpoints, and answers are not copied. Credential collections
and RunState flag candidates are not read by the extractor. Extraction requires
a terminal Run plus structured experiment and evidence state.

The SQL rule implements the required lesson:

```text
Database behavior should be identified before payload selection.
```

Extraction is explicit. R7 does not automatically write global memory after
every run and does not implement automatic learning.

## Store

`ExperienceStore` supports:

- `add`
- `add_many`
- `list`
- `query`
- `get`

Memory is persisted atomically as versioned JSON at the default location:

```text
experiences/experience.json
```

The `experiences/` directory is ignored by Git. Stable extractor IDs and
semantic checks prevent the same run/category/pattern from being added
repeatedly. Loaded records pass the same model and sensitive-data validation as
new records.

Experience is global memory and is never serialized into `run.json`,
`intelligence.json`, `experiments.json`, `artifacts.json`, or
`domain_runtime.json`.

## Retriever

`ExperienceRetriever` accepts:

- A `ChallengeSpec`.
- The selected Domain.
- Selected Skill names.
- Artifact metadata.
- An explicit result limit.

It ranks records using deterministic domain, category, Skill, and keyword
overlap. It uses no embedding, vector database, graph database, external
service, or LLM. Retrieval output is capped before Planner injection.

## Planner Integration

`JsonPlanner` receives Relevant Experience as a separate provider and prompt
section alongside Challenge, Intelligence, Skill Context, Domain Runtime
Context, and Experiment Context. Experience is explicitly labelled as
cross-run generic guidance, not current-challenge fact and not execution
authority.

The default global path is `./experiences/experience.json`; the default Planner
limit is five records. Local configuration may set:

```json
{
  "experience": {
    "path": "./experiences/experience.json",
    "max_context_items": 5
  }
}
```

The runtime only reads and retrieves from this store. It does not perform
implicit extraction or mutation.

## CLI

R7 adds read-only global-memory commands:

```bash
python main.py experience list
python main.py experience search sql
```

Both commands support an explicit `--store` path. Search also supports
`--domain` and `--limit`; it uses plain deterministic keyword matching.

## Tests

Deterministic tests cover:

- Rule-driven SQL Experience creation.
- Completed-run and experiment/evidence preconditions.
- JSON add, list, get, query, idempotence, and restore.
- Domain/category/Skill/keyword retrieval and result limits.
- Separate bounded Planner context injection.
- Sensitive record rejection.
- Credential exclusion from extracted records.
- IntelligenceState immutability during extraction and retrieval.
- Global-memory separation from per-run checkpoint files.
- Read-only CLI list and search behavior.
- The two-challenge fake-local creation and retrieval demo.
- Backward compatibility with the R0–R6 suite.

Final project virtual-environment validation:

```text
pytest -q              83 passed
pip check              PASS — No broken requirements found
python -m compileall . PASS
git diff --check       PASS
```

## Demo

`demos/r7_local_experience_loop.py` performs two deterministic local flows. It
does not open a socket, use an external target, load private data, or execute a
real exploit.

First challenge:

```text
Fake SQL challenge
  -> Hypothesis
  -> Failed UNION-style experiment
  -> Database-error evidence
  -> Rule-driven Experience extraction
  -> Global JSON store
  -> LOCAL_EXPERIENCE_CREATE_OK
```

Second challenge:

```text
New fake SQL parameter challenge
  -> Domain + Skill + keyword retrieval
  -> Previous generic SQL experience
  -> LOCAL_EXPERIENCE_RETRIEVE_OK
```

Complete output:

```text
LOCAL_EXPERIENCE_CREATE_OK
LOCAL_EXPERIENCE_RETRIEVE_OK
LOCAL_EXPERIENCE_LOOP_OK
```

## Security and Remaining Boundaries

- No API key, external target, private challenge data, credential, flag, secret,
  or real answer is stored.
- No fine-tuning, reinforcement learning, model training, or weight update is
  implemented.
- No Neo4j, graph database, knowledge graph, embedding, or vector search is
  implemented.
- No Skill file is modified by Experience memory.
- No Experience Agent or other multi-agent role is implemented.
- Experience quality is limited to the explicit deterministic rule catalog.
- Adding future rules requires tests that prove generic output and sensitive
  data exclusion.

**R7 COMPLETE — READY FOR EXPERIENCE EVOLUTION**
