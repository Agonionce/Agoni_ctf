# Agonionce R5 — Web Runtime Foundation

R5 is the first domain execution foundation. It can issue one structured HTTP
request to an authorized loopback CTF or local-lab target, capture evidence,
update Web lifecycle state, and produce deterministic Intelligence facts.

It does not include browser automation, Burp integration, a proxy, crawling,
directory discovery, vulnerability scanning, sqlmap, nuclei, MCP, automatic
submission, or public-target access.

## Architecture

```text
WebRuntime / WebRuntimeState
  ↓
Planner → ToolCall(http_request)
  ↓
PolicyEngine → WebRequestPolicy → ApprovalManager
  ↓
HTTPRequestTool
  ↓
RequestArtifact / ResponseArtifact / SessionArtifact
  ↓
ToolResult / Observation
  ↓
WebResponseAnalyzer → KnowledgeUpdater → IntelligenceState
```

The separation remains strict:

- Runtime owns `RECON → ANALYSIS → EXPLOITATION → VERIFY` lifecycle state.
- Skills provide Web reasoning guidance.
- `HTTPRequestTool` performs one structured request.
- Policy decides whether that request is allowed, needs approval, or is denied.
- Intelligence records evidence without automatically claiming a vulnerability.

## WebRuntimeState

The typed R5 state extends `DomainRuntimeState` with:

```text
base_url
endpoints
parameters and observed endpoint locations
cookies
technologies
current_phase (the inherited phase)
```

It does not copy R0 step history or R2 facts. Cookie values are persisted only
inside ignored local checkpoints and are masked from Planner context and CLI
output. `Question.url` becomes the declared `base_url` when provided.

## HTTPRequestTool

The Tool accepts structured fields:

```json
{
  "method": "GET or POST",
  "url": "http://127.0.0.1:PORT/path",
  "headers": {},
  "cookies": {},
  "params": {},
  "body": null,
  "timeout": 5
}
```

Limits and safety controls:

- only `http` and `https`;
- only loopback IP addresses or `localhost`;
- origin must match the current challenge's declared `base_url` or authorized target;
- no URL userinfo, fragment, redirect following, or public hostname;
- request and response size limits;
- timeout capped at ten seconds;
- managed transport headers and control characters rejected;
- GET and POST only.

The backend uses the Python standard-library HTTP client. It performs no
crawling, discovery, payload generation, or vulnerability logic.

## Policy

`WebRequestPolicy` applies before the Tool runs:

```text
plain loopback GET without query/body/cookies → ALLOW
POST or input-bearing/stateful request        → REQUIRE_APPROVAL
non-loopback or invalid target                → DENY
undeclared loopback origin                    → DENY
```

The Tool repeats loopback validation as defense in depth. Tests verify that an
unapproved POST never reaches the local Fake Server.

## Artifacts

Each completed request attempt writes three workspace JSON files:

```text
output/web/request-001.json   RequestArtifact
output/web/response-001.json  ResponseArtifact
output/web/session-001.json   SessionArtifact
```

ArtifactStore records the types `web_request`, `web_response`, and
`web_session`. Request Authorization and Cookie headers are redacted in the
request artifact. Response capture is bounded; redirects are observations and
are not followed automatically.

## Web intelligence

`WebResponseAnalyzer` deterministically extracts evidence-backed facts:

- endpoint;
- status code;
- parameter location;
- direct response reflection;
- technology header value.

It never labels a response as SQL injection, XSS, SSRF, authentication bypass,
or any other vulnerability. Such interpretations remain hypotheses produced
through the normal Analyzer and supported by evidence.

## CLI and validation

```bash
python main.py tools list
python main.py web status
pytest -q
```

`web status` shows phase, base URL, endpoints, parameter names, cookie names,
and technologies from the latest local checkpoint. It never prints cookie
values.
