# Agonionce R11 — Web Autonomous Research Foundation

## Result

R11 makes Web the first domain to combine a persistent application model,
bounded research context, typed experiments, provenance-bearing evidence,
session continuity, and reviewed challenge completion. It does not add a
scanner, crawler, browser, payload generator, exploit engine, public-target
automation, or automatic flag submission.

```text
Authorized Web Challenge
  -> Challenge Intake / contained Workspace
  -> controlled HTTP or captured fake-local observation
  -> Web Intelligence
  -> Web Application Model
  -> bounded Web Research Context
  -> research Hypothesis
  -> typed Web Experiment
  -> ToolRuntime / Policy / Approval / Sandbox boundary
  -> Artifact-backed generic and Web Evidence
  -> deterministic Evaluation
  -> Intelligence + Domain + Web research feedback
  -> next decision
```

## Architecture

R11 adds `agent/domains/web/research/`:

- `models.py` defines the application, session, experiment, evidence, and
  flag-candidate contracts;
- `session.py` manages origin-bound HTTP state without sending requests;
- `experiments.py` describes five non-executable Web experiment types;
- `evidence.py` projects controlled Tool metadata into provenance-bearing Web
  evidence;
- `manager.py` updates only `WebRuntimeState` from an Observation and Analyzer
  result;
- `context.py` builds the bounded, masked Planner view.

R11 also extends the existing Web Runtime state, HTTP Tool adapter, generic
EvidenceFactory, Planner context, read-only Web CLI, and Completion report. It
does not replace AgentRuntime, Planner protocol, ToolRuntime, PolicyEngine,
ApprovalManager, Sandbox, IntelligenceState, or ExperimentOrchestrator.

## Data Model

### Web Application Model

`WebApplicationModel` retains only structured, evidence-oriented state:

| Entity | Recorded state |
| --- | --- |
| Endpoint | path, methods, parameter names, observed status codes, authentication requirement, Artifact references |
| Parameter | name, observed endpoints and methods, Artifact references |
| Authentication | `UNKNOWN`, `ANONYMOUS`, `AUTHENTICATED`, `CHALLENGED`, or `EXPIRED`; active session ID and evidence references |
| Technology | name, passive indicator, source |
| Response Behavior | baseline/current request IDs, changed fields, bounded summary, Artifact references |
| Relationship | source, typed relation, target, Artifact references |

An endpoint accepting a parameter is represented as an explicit
`ACCEPTS_PARAMETER` relationship. Duplicate observations merge rather than
discarding earlier provenance. A technology entry remains evidence and is not
a vulnerability claim.

### Session State

`WebSessionState` supports:

- lifecycle: `CREATED`, `ACTIVE`, `AUTHENTICATED`, `EXPIRED`, `CLOSED`;
- authentication status;
- cookie continuity;
- controlled header continuity;
- observed CSRF/XSRF header and hidden-input state;
- exact origin binding.

`WebSessionManager` never calls an HTTP client. Production binds the current
WebRuntimeState session manager to the already registered `HTTPRequestTool`.
The Tool can accept an optional opaque `session_id`; it merges state only after
local-target and declared-origin validation, performs the ordinary approved
request, and then returns the response to the session manager.

Any `session_id` makes a request stateful. `WebRequestPolicy` therefore returns
`REQUIRE_APPROVAL`, even for a GET without parameters. A session cannot move
to another origin. Public targets remain denied by the existing loopback and
exact challenge-scope checks.

Cookie, authorization header, CSRF, and related values remain private runtime
data. The private session checkpoint and session Artifact can preserve values
needed for an authorized run, but `safe_dict`, Planner context, CLI tables,
Tool audit, Completion reports, and writeup drafts expose names and lifecycle
state only.

### Web Experiments

The first Web experiment taxonomy is:

| Type | Goal | Expected evidence class |
| --- | --- | --- |
| `ENDPOINT_ANALYSIS` | establish a bounded endpoint baseline | `ENDPOINT_DISCOVERED` |
| `PARAMETER_BEHAVIOR` | compare authorized local parameter behavior | `RESPONSE_BEHAVIOR` |
| `AUTHENTICATION_ANALYSIS` | observe access requirements | `AUTHENTICATION_STATE` |
| `RESPONSE_COMPARISON` | compare already controlled responses | `RESPONSE_BEHAVIOR` |
| `STATE_TRANSITION` | observe a permitted application/session transition | `STATE_TRANSITION` |

`WebExperimentCatalog` emits statements, goals, expected observations,
evidence types, confidence, and evidence value. It emits no Tool call, request,
shell command, payload, or approval decision. `DomainExperimentAdapter` uses
this catalog to supply phase-relevant candidates to the existing R10.2
prioritizer.

Planner `experiment_action` remains backward compatible and may add optional
`experiment_type`, `evidence_type`, and opaque `experience_influence` IDs. The
actual single ToolCall remains subject to all established execution controls.

## Research Loop and Runtime Integration

After each analyzed Web observation, the DomainRuntime adapter supplies both
the typed Observation and AnalysisResult to WebRuntime. The Web research
manager then:

1. merges endpoints, parameters, statuses, technologies, and relationships;
2. synchronizes passive R8 WebIntelligenceState into the application model;
3. creates `WebEvidenceRecord` objects only when Artifact references exist;
4. projects the current generic Experiment and Evaluation into a Web-specific
   view;
5. records Analyzer flag candidates with evidence-binding state;
6. leaves all IntelligenceState updates to the existing KnowledgeUpdater.

The Planner receives a bounded `WebResearchContext` containing:

- up to five modeled endpoints, parameters, technologies, behaviors, and
  relationships;
- masked session state;
- recent Web and generic Experiments;
- recent structured Web Evidence;
- masked flag-candidate IDs, digests, and verification state;
- bounded Intelligence summary;
- bounded, sanitized Experience retrieval.

This context is reasoning input only. It does not grant target scope or
execution authority.

## Evidence Flow

`HTTPRequestTool` and `WebIntelligenceTool` now emit bounded `web_evidence`
metadata in addition to their existing Artifacts. Examples are endpoint
discovery, parameter identification, session-state observation, and response
behavior difference.

```text
ToolResult
  +-- Artifact references (mandatory)
  +-- web_evidence metadata (observation only)
       |
       +-> R10.1 EvidenceFactory -> generic Experiment Evaluation
       +-> WebEvidenceFactory -> WebEvidenceRecord
```

The generic EvidenceFactory includes the structured Web observations in its
evidence text, allowing the existing deterministic Evaluator to classify an
expected observable such as `response behavior changed`. Evidence remains
distinct from a conclusion. Decisive generic Evaluation still requires
Artifact provenance.

## Flag Candidate and Completion Flow

R11 separates detection, evidence binding, and confirmation:

```text
Analyzer candidate
  -> DETECTED
  -> Artifact references present: EVIDENCE_BOUND
  -> existing explicit flag confirmer
       +-> accepted: VERIFIED
       +-> rejected: REJECTED
```

The runtime does not automatically submit a candidate. The existing
`flag_confirmer` remains the only confirmation boundary. In the authorized
local workbench, Completion records `status`, `candidate_count`, the confirmed
candidate value, its supporting evidence, and related artifact paths in the
private `report.md`/`writeup.md` projection. This local visibility does not
authorize submission and is not copied into global Experience or Planner
context.

## Checkpoint Recovery

No parallel checkpoint format was introduced. The following R11 state is
serialized inside the existing `domain_runtime.json`:

- application model;
- private session lifecycle;
- Web Experiment projections;
- Web Evidence records;
- private flag candidates and their verification state.

The ordinary `experiment_runtime.json` continues to own generic active
Hypotheses, Experiment history, Evaluation, feedback, and decision history.
On restore, old Web checkpoints without R11 fields remain valid and their
legacy endpoints, parameters, and technologies are projected into the new
application model.

## CLI and Observability

The existing read-only Web command group adds:

```bash
python main.py web model
python main.py web sessions
python main.py web experiments
python main.py web findings
```

Each accepts `--checkpoint <directory>`. `web model` displays modeled entities,
`web sessions` shows names and lifecycle only, `web experiments` shows typed
Experiment status and evidence count, and `web findings` shows structured Web
Evidence plus masked flag-candidate state.

## Demo

Run:

```bash
python demos/r11_web_autonomous_research.py
```

The deterministic demo performs actual Challenge Intake, creates a contained
workspace, and uses a fake non-network Tool through ToolRuntime in
`autonomous_local` mode:

```text
Challenge Intake
  -> fake-local endpoint observation
  -> Web Application Model
  -> Analyzer + Domain + Experience Hypothesis
  -> prioritized PARAMETER_BEHAVIOR experiment
  -> fake Tool through ToolRuntime and PolicyEngine
  -> Artifact-backed structured Evidence
  -> SUPPORTED Evaluation
  -> next research decision
  -> evidence-bound candidate + explicit local confirmation
  -> safe Completion verification metadata
```

It restores Web and Experiment checkpoint state and prints:

```text
LOCAL_WEB_AUTONOMOUS_RESEARCH_OK
```

The demo opens no socket and performs no exploitation.

## Security Boundary

R11 preserves these non-negotiable rules:

- only explicitly authorized, exact-origin loopback Web targets can reach the
  HTTP Tool;
- all HTTP requests enter ToolRuntime, schema validation, PolicyEngine,
  ApprovalManager when required, ArtifactStore, and audit;
- session state never establishes authorization and cannot cross origins;
- stateful requests always require approval;
- Domain Runtime, WebResearchManager, WebSessionManager, WebExperimentCatalog,
  and Experience retrieval cannot execute a Tool;
- no scanner, crawler, browser automation, JavaScript execution, payload
  database, exploit chain, public-target autonomy, or automatic flag
  submission exists;
- no Skill rewrite or Global Experience write occurs;
- session secrets and candidate values stay out of bounded contexts and
  generated completion documents.

## Tests

R11 coverage verifies:

- application model entity merging, relationships, and serialization;
- origin-bound session lifecycle, authentication transition, CSRF tracking,
  and safe masking;
- mandatory approval for session-backed HTTP requests;
- all five non-executable Web Experiment contracts;
- structured Web Evidence provenance and generic Evaluation participation;
- candidate detection, evidence binding, masking, and explicit verification;
- old-compatible domain checkpoint recovery;
- bounded Experience and Planner context integration;
- all four read-only CLI commands;
- the full fake-local intake-to-completion research loop.

Required validation commands:

```bash
pytest -q
python -m pip check
python -m compileall .
python main.py --help
python demos/r11_web_autonomous_research.py
git diff --check
git status --short
```

Final project-environment validation:

```text
.venv/bin/pytest -q
  156 passed
.venv/bin/python -m pip check
  No broken requirements found.
.venv/bin/python -m compileall -q .
  PASS
.venv/bin/python main.py --help
  PASS
.venv/bin/python demos/r11_web_autonomous_research.py
  LOCAL_WEB_AUTONOMOUS_RESEARCH_OK
git diff --check
  PASS
```

## Future Extension

The next safe step is validation against a dedicated local Docker challenge or
an explicitly authorized CTF instance. A future HTTP transport may support
additional methods or richer redirect semantics only through a reviewed Tool
contract and policy rules. Browser automation, crawling, automated payload
selection, and remote autonomy remain separate unimplemented roadmap work.

## Remaining Risks

- The application model is deterministic and may merge semantically different
  application states that share an endpoint path.
- Session authentication inference is intentionally conservative and cannot
  understand every custom login flow.
- CSRF discovery recognizes common headers and hidden input names; it does not
  execute JavaScript or interpret application code.
- Web Experiment selection and Evaluation remain lexical/rule-driven and may
  yield inconclusive or low-value research choices.
- `domain_runtime.json` contains private per-challenge session and candidate
  values and must remain in the ignored private checkpoint area.
- HTTP remains limited to GET/POST and loopback; redirects, browser behavior,
  real exploit automation, and public-target autonomy are not implemented.

**R11 COMPLETE — READY FOR REAL WEB CTF VALIDATION**
