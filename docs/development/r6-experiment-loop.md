# Agonionce R6 Completion Report

## Architecture

R6 adds an Experiment Layer between observations and the next planning
decision. It makes a proposed test, its expected outcome, its actual result,
and its evidence explicit rather than treating every Tool action as an
unstructured attempt.

```text
Observation
  |
  v
Hypothesis
  |
  v
Experiment
  |
  v
Evidence
  |
  v
Intelligence
```

The implemented service path is:

```text
Observation
  -> HypothesisManager
  -> ExperimentPlanner
  -> ToolRuntime / PolicyEngine / ApprovalManager
  -> ExperimentExecutor lifecycle record
  -> EvidenceCollector
  -> IntelligenceStore
  -> bounded Planner context
  -> Next Decision
```

`ExperimentManager`, `HypothesisManager`, `ExperimentPlanner`,
`ExperimentExecutor`, and `EvidenceCollector` manage reasoning state only.
They do not own a Tool registry and cannot call a Tool. Actual actions remain
behind the existing controlled execution boundary.

## Models

### Hypothesis

The existing R2 `Hypothesis` is the single hypothesis model and is extended for
R6 with `domain` and `evidence_refs`. R6-created hypotheses use numeric
confidence in the range 0.0–1.0. The governed lifecycle is:

```text
OPEN -> CONFIRMED
OPEN -> REJECTED
```

Closing a hypothesis requires one or more evidence IDs bound to that
hypothesis. Legacy R2 confidence/status data remains loadable for checkpoint
compatibility, but the R6 manager exposes only the governed lifecycle above.

### Experiment

`Experiment` stores `experiment_id`, `hypothesis_id`, `goal`, structured
`action`, `expected_result`, `actual_result`, timestamps, and status. Its
lifecycle is:

```text
PROPOSED -> RUNNING -> SUCCESS
                    -> FAILED
```

Invalid transitions fail closed. An experiment cannot close without an actual
result. The action is a proposal record and does not execute itself.

### Evidence

`EvidenceRecord` stores its source, observation, artifact references,
timestamp, evidence ID, experiment ID, and hypothesis ID. Evidence artifact
references create normal `ArtifactLink` records in `IntelligenceState`.

Evidence is deliberately not a conclusion. `EvidenceRecord` has no conclusion
field; confirmation or rejection happens only through the hypothesis
lifecycle after evidence has been bound.

## Planner Integration

`JsonPlanner` now accepts a separate R6 experiment context. The default
`ExperimentContextBuilder` provides only:

- Up to five current OPEN hypotheses.
- Up to five recent experiments.
- Up to eight recent evidence summaries.

The limits are explicit, validated, and included in the context. The Planner
prompt states that evidence is not a conclusion. Normal intelligence, skill,
domain runtime, and Tool schema contexts remain separate.

## Checkpoint

New checkpoints contain `experiments.json` in addition to the existing runtime,
intelligence, artifact, and optional domain runtime files:

```text
checkpoint/
├── run.json
├── intelligence.json
├── artifacts.json
├── experiments.json
└── domain_runtime.json       optional
```

`experiments.json` contains the challenge ID, schema version, hypotheses,
experiments, and evidence. Restore validates it against the structured
`IntelligenceState` and verifies hypothesis–experiment–evidence references.
Duplicate or inconsistent IDs, mismatched evidence bindings, and tampered
experiment snapshots are rejected. Older checkpoints without
`experiments.json` remain loadable.

## CLI

R6 adds read-only inspection commands that never execute Tools:

```bash
python main.py experiment list
python main.py hypothesis list
python main.py evidence list
```

Each command accepts `--checkpoint PATH` and otherwise uses the latest
checkpoint. `python main.py intelligence show` also reports experiment and
evidence counts.

## Tests

Deterministic tests cover:

- Hypothesis `OPEN -> CONFIRMED` lifecycle.
- Experiment `PROPOSED -> RUNNING -> SUCCESS` lifecycle.
- Fail-closed invalid lifecycle transitions.
- Evidence binding to experiments, hypotheses, and artifacts.
- `experiments.json` save, restore, consistency checks, and tamper rejection.
- Bounded Planner experiment context.
- Read-only experiment, hypothesis, and evidence CLI commands.
- The fake local Web experiment loop.
- Backward compatibility with the existing R0–R5 test suite.

Project virtual-environment validation results:

```text
pytest -q                 74 passed
python -m pip check       PASS — No broken requirements found
python -m compileall .    PASS
```

The host's unactivated global Python reports a pre-existing `zai-sdk`/`pyjwt`
version conflict. The project `.venv`, which is the repository-defined
development environment, passes `pip check`; no dependency files were changed
for R6.

## Demo

`demos/r6_local_experiment_loop.py` uses an authorized fake Web challenge at a
loopback-labelled target and an in-memory fake Tool. It does not open a socket,
contact an external target, or execute a real exploit. Both fake actions still
pass through ToolRuntime, PolicyEngine, and individual ApprovalManager
decisions.

The demonstrated sequence is:

```text
Fake Web observation: SQL error
  -> Hypothesis: SQL injection possible
  -> Experiment: test the id parameter with a controlled predicate
  -> Evidence: response differs from the SQL-error baseline
  -> Experiment SUCCESS
  -> Hypothesis CONFIRMED
```

Demo command and result:

```text
python -m demos.r6_local_experiment_loop
LOCAL_EXPERIMENT_LOOP_OK
```

## Security Boundary

- No API key, `.env` file, challenge secret, or external target is used.
- No scanner, exploit engine, payload generator, or real attack capability is
  added.
- The fake Tool is local, deterministic, in-memory, and registered only by the
  demo.
- Experiment state managers never bypass ToolRuntime, PolicyEngine,
  ApprovalManager, or workspace isolation.
- No automatic learning, model training, fine-tuning, reinforcement learning,
  weight update, knowledge graph, embedding system, skill rewriting, or
  multi-agent behavior is implemented.

## Remaining Risks

- No automatic learning or experience extraction exists.
- No skill evolution or automatic skill modification exists.
- No knowledge graph, graph database, vector database, or embedding retrieval
  exists.
- No real exploit automation or additional attack capability exists.
- Evidence quality still depends on the caller recording the correct controlled
  observation and source.
- Hypothesis confirmation is rule-governed but still requires a caller to make
  the explicit evidence-backed close decision.

**R6 COMPLETE — READY FOR EXPERIENCE FOUNDATION**
