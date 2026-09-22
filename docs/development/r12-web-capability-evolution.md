# Agonionce R12 — Web Capability Evolution

## Result

R12 evolves Web research from the R11 framework into a richer, deterministic
CTF analysis domain. It adds semantic Web knowledge, expanded non-executable
experiment contracts, structural response intelligence, a static fake-local
benchmark, reviewed Web experience extraction, and stronger CLI
observability.

R12 does not add a scanner, crawler, browser, JavaScript execution, payload
catalog, exploit engine, public-target automation, or automatic answer
submission.

```text
Authorized Web Challenge / fake-local capture
  -> HTTP Artifacts or static Benchmark captures
  -> HTML + JSON + error + state response intelligence
  -> Web Knowledge Model
  -> bounded Web Research Context
  -> typed research Hypothesis / Experiment proposal
  -> existing ToolRuntime / Policy / Approval boundary
  -> Artifact-backed Evidence and Evaluation
  -> Completion lessons
  -> sanitized Experience Candidate
  -> explicit human review
  -> optional Global Experience
```

## Architecture

R12 preserves the existing Runtime and execution contracts. Its new ownership
is contained in the Web Domain and Completion layers:

```text
agent/domains/web/intelligence/response.py
  structural response profiling and comparison

agent/domains/web/research/knowledge.py
  response-to-knowledge projection

agent/domains/web/research/models.py
  enhanced endpoint, parameter, authentication, transition, input, and behavior state

agent/domains/web/research/experiments.py
  expanded reasoning-only Web experiment catalog

agent/domains/web/benchmark/
  contained fixture loader, typed result model, deterministic passive runner

benchmarks/web/
  fake-local authentication, parameter, state, and business-logic fixtures

agent/completion/
  reviewed Web lesson and experience-candidate evolution
```

`WebResponseIntelligenceAnalyzer`, `WebKnowledgeModelEnhancer`, and
`WebBenchmarkRunner` are pure analysis components. They cannot invoke Tools,
open sockets, execute fixture source, or make approval decisions. A live local
HTTP action, when separately proposed, still passes through ToolRuntime,
schema validation, PolicyEngine, ApprovalManager, workspace containment,
ArtifactStore, and audit.

## Data Model

### Response Intelligence

`WebResponseProfile` retains only bounded structure:

- response format: `HTML`, `JSON`, `TEXT`, or `BINARY`;
- status, content type, and body length;
- bounded JSON key paths, not JSON values;
- common error-pattern names;
- common state-marker names;
- HTML form and link counts;
- request parameter names, locations, and coarse value shapes.

`WebStateDifference` compares two profiles by status, format, JSON key set,
error-pattern set, and state-marker set. Evidence remains an observation. A
parser error or state difference is not a vulnerability conclusion.

For backward compatibility, `WebIntelligenceTool` still creates the R8
four-artifact set. Profiles and state differences are stored in the existing
`response-diff.json` artifact and in `web_intelligence` metadata rather than
adding a fifth artifact.

### Web Knowledge Model

R12 extends `WebApplicationModel` with:

| Entity | Added knowledge |
| --- | --- |
| Endpoint | response formats, content types, access states, behavior tags |
| Parameter | input location, semantic roles, coarse shapes, user-controlled/reflected/affects-response state |
| Authentication | mechanisms, login/logout paths, protected paths, role indicators |
| State Transition | prior state, next state, observed event, endpoint, provenance |
| User-Controlled Input | name, endpoint, location, role, shape, behavior flags, provenance |
| Application Behavior | category, bounded observation, evidence type, provenance |
| Response Profile / Difference | checkpoint-safe structural response knowledge |

The first rule-driven parameter roles are `identifier`, `identity`,
`credential`, `file`, `navigation`, `business`, `pagination`, `state_token`,
and `generic`. Classification uses parameter names and coarse input shape; it
does not retain request values or claim exploitability.

All new fields use backward-compatible defaults. They are serialized in the
existing `domain_runtime.json`, so R11 checkpoints restore and R12 state
survives the ordinary domain checkpoint path.

## Research Flow

Captured HTTP results now carry a structural response profile in ToolResult
metadata. `WebResearchManager` combines it with passive Web Intelligence and
projects it into the application model:

```text
RequestArtifact + ResponseArtifact
  -> WebResponseProfile
  -> endpoint response structure
  -> parameter location / shape / semantic role
  -> authentication and access state
  -> application behavior
  -> optional structural state transition
  -> bounded Planner context
```

The Web research context includes bounded recent endpoints, parameters,
state transitions, user inputs, application behaviors, response profiles, and
response differences. It continues to mask session and candidate values and
grants no execution authority.

The read-only Analyzer may add response-structure facts, error-pattern facts,
state-difference findings, and OPEN parser-behavior hypotheses. It never turns
an error pattern into a confirmed weakness.

## Experiment Extensions

R12 retains all R11 types and adds:

| Type | Research question | Evidence class |
| --- | --- | --- |
| `INPUT_BEHAVIOR_ANALYSIS` | how a user-controlled input affects bounded response structure | `INPUT_BEHAVIOR` |
| `AUTHORIZATION_ANALYSIS` | which observed access state governs an endpoint | `AUTHORIZATION_STATE` |
| `FILE_PROCESSING_ANALYSIS` | which local input shape and processing outcome are observed | `FILE_PROCESSING` |
| `PARSER_BEHAVIOR_ANALYSIS` | which format or parser error pattern is observed | `PARSER_BEHAVIOR` |
| `BUSINESS_LOGIC_ANALYSIS` | which bounded application-state difference is observed | `BUSINESS_LOGIC` |

Each proposal carries `goal`, structured `context`, `expected_result`, and
`evidence_type`. It carries no Tool name, request, payload, or execution
authority. Planner output can preserve the optional experiment context while
remaining compatible with older experiment actions.

## Benchmark Design

`benchmarks/web/` defines a repository-owned, local-only contract:

```text
case/
  challenge.json          metadata and source/capture paths
  environment.json        kind=fake-local, network=disabled
  expected_behavior.json  structural expectations
  captures.json           static request/response pairs
  source/                 non-executed explanatory source files
```

The loader validates normalized IDs, contained relative paths, fixture
existence, and the mandatory fake-local/network-disabled environment. Symlink
fixtures and path traversal are rejected. The runner reads static captures,
builds Web Intelligence and the Web Knowledge Model, evaluates typed expected
behavior, and optionally writes a JSON result record. It never imports or
executes fixture source and never starts a server.

The initial cases are:

- `authentication` — protected endpoint and authorization response evidence;
- `parameter_behavior` — user-controlled query and response comparison;
- `state_transition` — anonymous-to-authenticated structural transition;
- `business_logic` — business-role inputs and application-state behavior.

Generated records go to the ignored `benchmark-results/web/` directory by
default. They are local validation data, not committed challenge answers.

## Experience Integration

The R8.6 review boundary remains unchanged:

```text
Completion Report
  -> deterministic lessons
  -> rule-driven Web Experience Candidate
  -> PENDING
       +-> explicit approve -> sanitized Global Experience
       +-> explicit reject  -> retained rejected decision
```

New sanitized candidate categories cover authorization analysis, parameter
behavior, file processing, parser behavior, business logic, and failed Web
experiments. Both successful and failed experiments can produce generic
lessons. Candidates still reject sensitive terminology and values, never
contain challenge answers, and cannot enter Global Experience automatically.

## CLI

R12 retains `web experiments` and `web findings`, and adds:

```bash
python main.py web context
python main.py web benchmark
python main.py web benchmark authentication
```

`web context` displays the same bounded and sanitized research view available
to planning. `web benchmark` without an ID lists fake-local cases. With an ID,
it evaluates static captures and writes an ignored result record. Existing
checkpoint-based Web commands continue to accept `--checkpoint`.

## Demo

Run:

```bash
python demos/r12_web_capability_evolution.py
```

The demo first runs the existing fake-local Challenge Intake, AgentRuntime,
Experiment, Evidence, Evaluation, checkpoint, and Completion flow. It then
evaluates all four static cases, writes results only to a temporary directory,
extracts sanitized Web experience candidates from a synthetic local Completion
report, performs explicit approval, and verifies the Global Experience write.
It prints:

```text
LOCAL_WEB_CAPABILITY_EVOLUTION_OK
```

## Security Boundary

- benchmark fixtures must declare `kind=fake-local` and `network=disabled`;
- fixture source is never executed;
- benchmark paths are contained and traversal/symlinks are rejected;
- response profiles retain keys, names, shapes, and patterns rather than
  private values;
- no new network Tool or ToolRuntime bypass exists;
- public targets remain denied by the existing Web policy;
- evidence remains separate from findings and hypotheses;
- Experience candidates require review and sensitive data remains rejected;
- automatic exploitation, answer submission, Skill modification, and model
  training remain absent.

## Tests

R12 coverage verifies:

- JSON/HTML response understanding, error patterns, and state differences;
- endpoint, parameter, authentication, input, behavior, and transition state;
- all expanded Experiment contracts and their non-executable context;
- bounded Planner context;
- R12 checkpoint round-trip and R11 compatibility;
- all four fake-local benchmark cases and result records;
- benchmark path-containment denial;
- successful and failed Web experience extraction;
- explicit approve/reject behavior and Global Experience isolation;
- benchmark CLI and end-to-end local demo;
- the unchanged R8 four-artifact Tool contract.

Validation result from the project `.venv`:

```text
source .venv/bin/activate

pytest -q
  165 passed

python -m pip check
  No broken requirements found.

python -m compileall .
  PASS

python demos/r12_web_capability_evolution.py
  LOCAL_WEB_CAPABILITY_EVOLUTION_OK

git diff --check
  PASS
```

## Remaining Risks

- Parameter semantics are deterministic name-based heuristics and may be
  incomplete or ambiguous.
- JSON understanding records bounded key paths but does not infer a complete
  API schema.
- State markers are lexical; custom application states may remain unknown or
  require human interpretation.
- Static captures measure deterministic model behavior, not browser rendering,
  JavaScript, redirects, race conditions, or server-side timing.
- The initial benchmark has four small cases and does not yet measure solve
  rate, research efficiency, or complete challenge completion.
- Experiment selection and evaluation remain rule-driven and may produce
  inconclusive choices.
- Real Web CTF validation is still limited to explicitly authorized targets
  and requires existing Tool policy and review boundaries.

**R12 COMPLETE — READY FOR WEB CTF BENCHMARK**
