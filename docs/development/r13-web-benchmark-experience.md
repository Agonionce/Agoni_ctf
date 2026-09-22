# Agonionce R13 — Web Benchmark & Experience Evolution

## Result

R13 establishes an auditable Web evaluation and Experience-quality cycle:

```text
Fake-local or explicitly authorized Challenge
  -> controlled Agent Research Run
  -> sanitized Completion
  -> Benchmark Evaluation Record
  -> rule-driven Lesson Candidates
  -> reviewed Experience
  -> explicit run feedback
  -> Experience effectiveness context for a future run
```

The phase adds no scanner, crawler, payload catalog, exploit engine, browser
automation, public-target execution, automatic answer submission, LLM-based
lesson extraction, or automatic Experience approval.

## Benchmark Architecture

R13 extends `agent/domains/web/benchmark/` with three contracts:

- `WebBenchmarkRunSnapshot` normalizes one completed research run;
- `WebBenchmarkEvaluationRecord` stores challenge metadata, result, solved
  status, experiments, Evidence, Hypotheses, Tool counts, duration, Experience
  usage, expectation checks, and Web model summary;
- `WebBenchmarkReportBuilder` aggregates persisted evaluation history.

```text
Challenge metadata + environment + expected behavior + evaluation policy
  -> static captured request/response evidence
  -> Web Intelligence / Web Knowledge Model
  -> expectation checks
  + completed Agent Run snapshot
  -> Evaluation Record
  -> latest result + append-only history record
```

`WebBenchmarkRunner` remains passive: it reads static repository fixtures,
does not execute source files, opens no socket, and calls no Tool. For a real
authorized run, `WebBenchmarkRunSnapshot.from_completion` accepts sanitized
Completion, Hypothesis, and audit data. It does not mutate Runtime,
IntelligenceState, or the Completion report.

Results are written under the ignored `benchmark-results/web/` tree:

```text
benchmark-results/web/
  authentication.json
  history/
    authentication/
      evaluation-<id>.json
```

The latest file supports inspection; history supports trend reporting. Run
content is recursively masked before persistence. The Evaluation Record stores
opaque Experience and Evidence references, never authority to reuse them.

## Evaluation Model

An evaluation is solved only when all are true:

1. the run reports a solved result;
2. every expected structural behavior passes;
3. the benchmark's minimum Evidence count is satisfied.

Every case contains:

```text
challenge.json
environment.json
expected_behavior.json
evaluation.json
captures.json
source/
```

`environment.json` must declare `kind=fake-local` and `network=disabled`.
`evaluation.json` currently requires `solved_when=all_expectations_pass` and a
positive `minimum_evidence`. Paths remain contained; fixture symlinks and path
traversal remain rejected.

The benchmark catalog now covers:

- authentication;
- authorization;
- parameter behavior;
- session state;
- file processing;
- JSON API behavior;
- business logic;
- explicit state transition.

These are small deterministic capability fixtures, not exploit challenges.

## Performance Reporting

Run:

```bash
python main.py benchmark list
python main.py benchmark run authentication
python main.py benchmark report
```

The aggregate report displays:

- distinct challenges and total runs;
- solved runs and success rate;
- average Experiment and Evidence counts;
- average duration;
- total Tool calls;
- Experience usage count and usage rate;
- improvement delta and `IMPROVING`, `STABLE`, `DECLINING`, or
  `INSUFFICIENT_DATA` trend.

The trend compares earlier and recent halves of chronological history. It is a
descriptive measurement, not a statistically validated claim of model
improvement.

## Lesson Extraction

`LessonExtractor` reads only persisted Completion fields and generates typed,
provenance-bearing candidates:

| Kind | Source |
| --- | --- |
| `SUCCESSFUL_STRATEGY` | a successful Experiment and its Evidence |
| `FAILED_STRATEGY` | a failed Experiment and its Evidence |
| `GENERAL_INSIGHT` | an evidence-backed Finding |

Each `LessonCandidate` records its source Challenge, Evidence references,
Experiment references, statement, rationale, and confidence. Extraction is
deterministic and uses no LLM. Sensitive terminology is rejected.

Completion now writes `lesson_candidates.json` beside `lessons.md` and passes
their provenance into Experience-candidate extraction. `lessons.md` remains a
human-readable summary; candidates remain structured and reviewable.

## Experience Lifecycle

Approved Experience text remains immutable in the R7 `experience.json`
format. R13 stores quality separately in `experience-quality.json`:

```text
Approved Experience
  -> source Challenge and source Evidence
  -> used by a later Run
  -> explicit SUCCESS / FAILURE / INCONCLUSIVE feedback
  -> usage and validation counts
  -> success/failure association
  -> effectiveness and bounded confidence update
  -> bounded future retrieval context
```

`ExperienceQualityRecord` contains:

- source Challenge and Evidence IDs;
- use and validation counts;
- success, failure, and inconclusive counts;
- effectiveness (`success / decisive validations`);
- feedback IDs and updated time;
- bounded feedback-adjusted confidence.

`ExperienceFeedbackRecord` binds every update to one approved Experience,
source Run, source Challenge, outcome, solved state, and Evidence IDs. Repeated
feedback for the same Experience/Run/Challenge is idempotent.

Successful feedback nudges confidence upward; failed feedback nudges it
downward; inconclusive feedback changes counts but not confidence. Approved
Experience content is never rewritten. `ExperienceRetriever` may include this
bounded quality summary and use effectiveness as a small deterministic ranking
signal.

Feedback is never automatic by default. It occurs only through an explicit API
call, `experience feedback`, or `benchmark run --apply-feedback` with approved
Experience IDs and both stores present.

CLI:

```bash
python main.py experience quality
python main.py experience feedback <experience-id> \
  --outcome SUCCESS \
  --source-run <run-id> \
  --source-challenge <challenge-id> \
  --solved \
  --evidence <evidence-id>
```

## Demo

Run:

```bash
python demos/r13_web_benchmark_experience.py
```

The demo:

1. creates one approved synthetic local Experience;
2. evaluates a successful and failed research snapshot using that Experience;
3. explicitly records both feedback outcomes;
4. runs the remaining fake-local benchmark catalog;
5. aggregates performance history;
6. verifies Experience use, effectiveness, and confidence state;
7. extracts successful, failed, and general Lesson Candidates.

Output:

```text
LOCAL_WEB_BENCHMARK_EXPERIENCE_EVOLUTION_OK
```

## Security Boundary

- all benchmark fixtures remain static, fake-local, and network-disabled;
- source files are explanatory and are never imported or executed;
- a benchmark result does not grant Tool, target, or Runtime authority;
- live actions still require ToolRuntime, PolicyEngine, ApprovalManager,
  containment, ArtifactStore, and audit;
- evaluation data is masked and must stay in ignored local storage;
- Experience feedback accepts opaque IDs rather than private values;
- only already approved Experience can receive quality feedback;
- Lesson and Experience Candidates still require sanitization and review;
- no automatic Experience merge, Skill rewrite, model training, or weight
  update exists.

## Tests

R13 adds coverage for:

- eight-case benchmark catalog and per-case evaluation policy;
- complete Evaluation Record fields and history persistence;
- Completion-to-Run snapshot adaptation;
- performance aggregation and improvement trend;
- Experience provenance, idempotent feedback, effectiveness, and confidence;
- quality-aware bounded retrieval;
- successful, failed, and general Lesson Candidates with provenance;
- Benchmark and Experience CLI workflows;
- the complete fake-local R13 demo;
- all R0-R12 regression tests.

Project `.venv` validation:

```text
pytest -q
  173 passed

python -m pip check
  No broken requirements found.

python -m compileall -q .
  PASS

python demos/r13_web_benchmark_experience.py
  LOCAL_WEB_BENCHMARK_EXPERIENCE_EVOLUTION_OK

git diff --check
  PASS
```

## Future Research Direction

- bind an explicitly authorized real Web CTF Completion snapshot to the same
  Evaluation Record without changing its schema;
- add repeated controlled runs per benchmark to measure variance;
- separate model/prompt/tool version metadata for comparable evaluations;
- introduce confidence calibration based on a larger validation history;
- add reviewed quality reset or correction workflows without deleting audit
  history;
- grow benchmark cases while keeping fixtures local, deterministic, and free
  of challenge answers.

## Remaining Risks

- eight fixtures are too small to predict real Web CTF solve rate;
- static captures do not measure live server interaction, browser behavior,
  redirects, timing, concurrency, or JavaScript;
- success-rate trends are descriptive and sensitive to run ordering and sample
  size;
- Experiment, Evidence, and Tool counts are only as complete as the supplied
  Completion and audit snapshot;
- Experience effectiveness is association, not proof of causation;
- lexical Lesson extraction can miss nuanced strategies or produce generic
  candidates;
- real Web validation remains restricted to explicit authorization and the
  established execution boundary.

**R13 COMPLETE — READY FOR REAL WEB CTF VALIDATION**
