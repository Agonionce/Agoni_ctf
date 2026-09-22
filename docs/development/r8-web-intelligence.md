# Agonionce R8 Completion Report

## 1. Result

R8 upgrades the authorized-local Web path from request/response capture to a
passive Web application understanding loop. Agonionce can now parse captured
HTML, map a same-origin attack surface, retain evidence-only technology
indicators, compare response behavior, propose an OPEN Web hypothesis, and feed
the result into the existing R6 Experiment Loop.

R8 is not a vulnerability scanner or exploit engine. It adds no browser
automation, Burp integration, crawler, directory brute force, public-target
capability, payload database, or automatic exploit chain.

## 2. Architecture

```text
Authorized Local Web Challenge
  |
  v
HTTPRequestTool
  |
  v
Request / Response / Session Artifacts
  |
  v
ToolRuntime -> PolicyEngine -> ApprovalManager
  |
  v
WebIntelligenceTool
  |
  v
WebIntelligenceManager
  |
  +-- HTMLAnalyzer
  +-- EndpointMapper
  +-- TechnologyDetector
  +-- ResponseBehaviorAnalyzer
  |
  v
WebIntelligenceState / WebAttackSurface
  |
  v
WebResponseAnalyzer -> KnowledgeUpdater -> IntelligenceState
  |
  v
OPEN Hypothesis -> Experiment -> Evidence -> Next Decision
```

The boundary is deliberate: `WebIntelligenceManager` consumes typed artifacts
and coordinates pure analysis only. It never invokes a Tool, opens a network
connection, writes IntelligenceState, or executes JavaScript. The registered
`web_intelligence` Tool is the controlled filesystem adapter. It resolves every
input within the challenge workspace and produces audited artifacts through
ArtifactStore.

## 3. Web Intelligence Components

### HTMLAnalyzer

`HTMLAnalyzer` accepts a `ResponseArtifact` and deterministically extracts:

- page title;
- forms, actions, methods, and named inputs;
- links;
- script sources and inline-script presence;
- bounded HTML comments.

It uses a parser only and never runs JavaScript.

### EndpointMapper

`EndpointMapper` merges HTML links, forms, script sources, captured request
artifacts, and optional prior endpoint evidence. Only same-origin HTTP/HTTPS
paths enter the map. Request artifacts receive the strongest observation
confidence; passive HTML discoveries remain evidence with lower confidence.
No endpoint is contacted by the mapper.

### TechnologyDetector

`TechnologyDetector` records bounded indicators from `Server`,
`X-Powered-By`, and generator headers, HTML markers, and cookie names. Evidence
may indicate Flask, Werkzeug, PHP, SQLite, nginx, Apache, or WordPress. It does
not infer versions as vulnerabilities and never stores cookie values in Web
intelligence output.

### ResponseBehaviorAnalyzer

The behavior analyzer compares captured response status, body length, title,
content digest, and bounded error signatures. A database-related difference
produces the Finding `Possible database-related behavior`. The Finding states
that an experiment is required and does not claim confirmed SQL injection.

## 4. Intelligence Models

R8 adds:

- `EndpointFinding(path, method, parameters, source, confidence)` to the
  per-challenge `IntelligenceState` with artifact provenance and JSON restore;
- `HTMLForm` and `HTMLAnalysis` for parsed document structure;
- `TechnologyEvidence` for evidence-only technology indicators;
- `ResponseDifference` and `BehaviorFinding` for comparisons;
- `HypothesisProposal` for bounded, non-terminal analyzer proposals;
- `WebAttackSurface` for endpoint, parameter, and technology organization;
- `WebIntelligenceState` as the Web runtime's typed aggregate.

`WebRuntimeState` checkpoints and restores the aggregate through
`domain_runtime.json`. Endpoint findings also enter `IntelligenceState` through
`KnowledgeUpdater`; repeated observations of the same method/path merge their
parameters, sources, confidence, and artifact references.

The Web attack-surface Planner provider has explicit endpoint, parameter, and
technology limits. The prompt labels all entries as observations rather than
vulnerability verdicts or execution authority.

## 5. Experiment Integration

When response comparison observes a database-related error difference for a
captured parameter, `WebResponseAnalyzer` may propose:

```text
Parameter id may influence a database query
```

The proposal enters IntelligenceState as an OPEN hypothesis with non-terminal
confidence. No request or experiment is executed automatically. The existing
`ExperimentManager` remains responsible for proposal, start, evidence binding,
result recording, and evidence-backed closure. Any experiment action still
passes through ToolRuntime, PolicyEngine, ApprovalManager, workspace isolation,
and audit logging.

The Web phases remain:

```text
RECON        endpoints + parameters + technology evidence
ANALYSIS     findings + hypotheses + experiment proposal
EXPLOITATION explicitly approved controlled experiment
VERIFY       evidence review + FlagCandidate
```

## 6. CLI

R8 adds read-only checkpoint views:

```bash
python main.py web surface
python main.py web endpoints
python main.py web technologies
python main.py hypothesis list
```

The three Web commands accept `--checkpoint PATH`. Cookie values remain masked
in `web status`; technology output contains evidence text and source only.

## 7. Demo

`demos/r8_local_web_intelligence_loop.py` starts a real Flask application bound
to an ephemeral `127.0.0.1` port. It exposes only the fake local routes:

```text
/
/login
/article?id=
/admin
```

The demo captures the root and two deterministic article responses, runs
passive analysis through ToolRuntime, stores the attack surface and Finding,
creates an experiment from the analyzer-proposed hypothesis, binds analysis
artifacts as evidence, and reaches VERIFY with a local FlagCandidate.

The analysis Tool writes and ArtifactStore registers:

```text
output/web/html-analysis.json
output/web/endpoint-map.json
output/web/technology.json
output/web/response-diff.json
```

Run:

```bash
source .venv/bin/activate
python -m demos.r8_local_web_intelligence_loop
```

Expected output:

```text
LOCAL_WEB_INTELLIGENCE_LOOP_OK
```

## 8. Tests

Deterministic R8 coverage verifies:

- form, input, link, script, comment, and title extraction;
- same-origin endpoint mapping and external-link exclusion;
- request-backed parameter confidence;
- header, HTML, and cookie-name technology evidence;
- response status, length, title, content, and error differences;
- Finding, EndpointFinding, and OPEN Hypothesis integration;
- artifact provenance and four ArtifactStore registrations;
- bounded Web attack-surface Planner context;
- WebIntelligenceState checkpoint restore;
- read-only Web CLI views;
- the real Flask application on localhost only;
- compatibility with the R0-R7 suite.

Final project virtual-environment validation:

```text
pytest -q              92 passed
python -m pip check    PASS
python -m compileall . PASS
git diff --check       PASS
```

## 9. Remaining Risks

- Technology detection is signature-based evidence and may have false
  positives or miss custom stacks.
- HTML parsing does not execute JavaScript, so client-rendered routes are not
  discovered.
- Endpoint mapping is passive and does not crawl, brute-force, or validate
  route reachability.
- Response differences require explicit experiment design before any
  conclusion.
- No automatic learning, Skill evolution, knowledge graph, embedding, vector
  search, model-weight update, browser automation, scanner, payload database,
  or exploit automation is implemented.
- Public targets remain denied by the R5 loopback policy; real Web research
  validation requires an explicitly authorized future phase.

**R8 COMPLETE — READY FOR REAL WEB RESEARCH VALIDATION**
