# AGENTS.md — Agonionce Engineering Constitution

## Authority and Purpose

This document is the highest-level engineering guidance for Agonionce. It
governs architecture, development, validation, security boundaries, and future
extension. It is written for Codex, Claude Code, human contributors, and future
AI development agents.

When a proposed change conflicts with this document, preserve the constraints
in this document unless the project maintainers explicitly amend the
governance first. Keep implementation, tests, demos, and documentation aligned
with these rules.

## Project Identity

Agonionce is an **AI-assisted CTF research and security learning framework**.
It combines structured reasoning, persistent challenge intelligence, and
controlled execution to help solve and study security challenges safely and
reproducibly.

Agonionce is intended for:

- Authorized CTF competitions.
- Local CTF laboratories.
- Security coursework.
- Explicitly permitted security research.
- Defensive security experimentation.

Agonionce is not a general-purpose network attack tool. It is not intended for:

- Unauthorized targets or activity outside an explicitly granted scope.
- Real-world attack automation.
- Scanning unknown systems.
- Exploitation without permission.
- Hiding actions, bypassing approvals, or avoiding auditability.

Features that cannot be kept within the authorized CTF and security-learning
scope do not belong in the project.

## Core Philosophy

Agonionce is not an LLM with a shell executor. Its design is the combination of:

```text
Reasoning
  +
Knowledge
  +
Controlled Execution
  +
Evidence-based Learning
```

The core decision loop is:

```text
Challenge
   |
   v
Domain Understanding
   |
   v
Planning
   |
   v
Controlled Tool Execution
   |
   v
Observation
   |
   v
Hypothesis
   |
   v
Experiment Proposal
   |
   v
Approval and Controlled Tool Execution
   |
   v
Evidence
   |
   v
Intelligence Update
   |
   v
Next Decision
```

Reasoning proposes actions; it does not grant permission to execute them.
Observations provide evidence; they are not automatically facts. Confirmed
facts, findings, and unresolved hypotheses must remain distinguishable so that
each next decision is traceable to evidence.

Completed runs may contribute only sanitized, generic experience through a
separate rule-driven path:

```text
Completed Run
  -> Experience Extraction
  -> Global Experience Store
  -> Bounded Retrieval for a Later Challenge
```

## System Architecture

The conceptual architecture is:

```text
Agonionce
|
+-- Runtime Layer
|   +-- Agent execution loop
|   +-- Planning
|   +-- Observation
|
+-- Challenge Intake Layer
|   +-- Challenge manifests
|   +-- Workspace bootstrap
|   +-- Per-challenge run records
|
+-- Intelligence Layer
|   +-- Facts
|   +-- Findings
|   +-- Hypotheses
|   +-- Challenge memory
|
+-- Experiment Layer
|   +-- Hypothesis lifecycle
|   +-- Experiment proposals and results
|   +-- Evidence provenance
|   +-- Bounded autonomous research decisions
|
+-- Completion Layer
|   +-- Completed-run collection
|   +-- Evidence-bound reports and writeup drafts
|   +-- Reviewed experience candidates
|
+-- Experience Layer
|   +-- Cross-run patterns
|   +-- Reusable strategies and lessons
|   +-- Sanitized failure memory
|
+-- Domain Layer
|   +-- Web
|   +-- Pwn
|   +-- Reverse
|   +-- Crypto
|   +-- Misc
|
+-- Skill Layer
|   +-- Domain reasoning knowledge
|   +-- Strategies
|   +-- Heuristics
|
+-- Execution Layer
|   +-- Tools
|   +-- Policies
|   +-- Approval
|
+-- Environment Layer
    +-- Local tools
    +-- Sandbox
    +-- Future MCP connections
```

### Layer Responsibilities

- **Runtime Layer:** owns orchestration, planning cycles, observations,
  lifecycle transitions, phase state, and typed contracts. It coordinates
  other layers without absorbing their responsibilities.
- **Challenge Intake Layer:** validates explicit user-provided challenge
  metadata and local inputs, creates contained workspaces through
  `WorkspaceManager`, produces `ChallengeSpec`, and initializes private
  per-challenge run records. It never executes imported content or grants Tool
  authority.
- **Intelligence Layer:** stores evidence-backed challenge knowledge, including
  facts, findings, hypotheses, artifacts, checkpoints, and challenge memory. It
  must preserve provenance and uncertainty.
- **Experiment Layer:** turns observations into explicit hypotheses and bounded
  experiment proposals, ranks evidence value, and records results and feedback
  without executing a Tool itself. Evidence remains separate from conclusions.
- **Completion Layer:** reads completed per-challenge state and creates
  deterministic reports, evidence-bound writeup drafts, lessons, and sanitized
  experience candidates. It does not mutate Runtime or Intelligence state, and
  candidates require explicit review before entering global Experience.
- **Experience Layer:** extracts sanitized, generic patterns, strategies,
  lessons, and failures from completed runs. It stores global JSON memory
  separately from current-challenge IntelligenceState and retrieves a bounded
  relevant view without embeddings.
- **Domain Layer:** organizes domain-specific lifecycle state and analysis for
  Web, Pwn, Reverse, Crypto, and Misc challenges. A domain runtime coordinates
  state; it does not execute tools or embed exploit logic.
- **Skill Layer:** supplies non-executable domain knowledge, strategies, and
  heuristics to reasoning. Skills guide decisions but cannot perform actions.
- **Execution Layer:** exposes first-class tools and applies policy, approval,
  workspace containment, and normalized observations to every action.
- **Environment Layer:** contains the local binaries, sandboxes, Docker or VM
  environments, and future external tool connections in which approved actions
  run. It never grants authority by itself.

### Repository Mapping

```text
agent/runtime/       typed orchestration, planning, observations, contracts
agent/challenge/     R8.5 challenge manifests, intake, workspace, run binding
agent/intelligence/  structured knowledge, evidence, and checkpoints
agent/intelligence/experiment/  R6 hypothesis, experiment, evidence lifecycle
agent/intelligence/experiment/runtime/  R10.2 execution, evaluation, feedback, and research loop
agent/completion/    R8.6 read-only completion reports and candidate review
agent/experience/    R13 reviewed memory, separate quality feedback, and retrieval
agent/domains/       domain intelligence and lifecycle state
agent/domains/web/intelligence/  R8 passive Web application understanding
agent/domains/web/research/  R12 application knowledge, sessions, experiments, and Web evidence
agent/domains/web/benchmark/  R13 fake-local evaluation records, history, and reporting
benchmarks/web/       non-executed fake-local Web fixtures, expectations, and evaluation policy
skill/, skills/      skill discovery and non-executable domain instructions
agent/tools/         first-class tool contracts and ToolRuntime execution
agent/policy/        policy decisions and action-level approval
agent/workspace/     challenge workspace isolation
agent/artifacts/     artifact metadata
cli/                 Typer commands and terminal interaction
ctf_platform/        challenge input and flag submission adapters
prompts/             active Planner and Analyzer prompt contracts
tests/               deterministic unit and local integration validation
webui/               R14 loopback-only Presentation Layer and safe projections
```

The current orchestration path is:

```text
AgentRuntime
  -> Planner
  -> ToolRuntimeExecutor
  -> PolicyEngine
  -> ApprovalManager
  -> Tool
  -> Observation / Analyzer
  -> KnowledgeUpdater / IntelligenceState
  -> SkillRouter / SkillContextBuilder
  -> DomainRuntimeManager / DomainRuntimeContextBuilder
  -> next Planner decision
```

The current Web path preserves this same execution boundary while adding
passive application understanding and R12 research state:

```text
HTTPRequestTool
  -> Request / Response / Session artifacts
  -> WebIntelligenceTool through ToolRuntime
  -> WebIntelligenceManager (pure analysis coordinator)
  -> HTMLAnalyzer / EndpointMapper / TechnologyDetector
  -> ResponseBehaviorAnalyzer / WebResponseIntelligenceAnalyzer
  -> WebIntelligenceState / EndpointFinding / bounded Planner context
  -> WebResponseAnalyzer suggestions
  -> KnowledgeUpdater / IntelligenceState
  -> WebKnowledgeModelEnhancer
  -> WebApplicationModel + masked session lifecycle + WebResearchContext
  -> typed Web Experiment proposal
  -> ExperimentOrchestrator / EvidenceFactory / Evaluation
  -> WebEvidenceRecord + next decision
```

`WebIntelligenceManager` analyzes already captured artifacts. It does not call
Tools, open sockets, execute JavaScript, or mutate IntelligenceState directly.
`WebIntelligenceTool` is the controlled adapter that validates workspace paths,
writes analysis artifacts, and enters the ordinary policy, approval, audit,
and ArtifactStore flow.

R11 `WebResearchManager`, `WebExperimentCatalog`, and `WebSessionManager` are
state coordinators, not execution backends. Persistent HTTP state may be used
only by a runtime-bound `HTTPRequestTool`; a `session_id` makes the action
stateful and therefore requires action-level approval. Sessions are bound to
one declared loopback origin. Cookie, header, and CSRF values remain masked
from Planner context and CLI output. In the explicitly authorized local R14
workbench, ordinary challenge-local outcome and completion views deliberately
show every value already persisted as evidence, including the final Flag,
supporting text, credential/header material, and evidence or analysis-material
paths, so the operator can verify the run manually. Those values remain
challenge-local and are never copied into global Experience.

R12 response intelligence and benchmark components are passive analyzers. They
may read captured fake-local request and response fixtures, classify bounded
structure, and produce result records. They must not execute fixture source,
start a server, open a socket, or call a Tool. Benchmark fixtures must declare
`kind=fake-local` and `network=disabled`; paths must remain contained and
generated result records must remain ignored local data.

R13 Benchmark Evaluation records may consolidate only sanitized Completion,
Intelligence, audit, and static-fixture metadata. They do not authorize an
action. Benchmark history belongs in ignored local result storage. Performance
trends are descriptive measurements and must not be represented as proof of
general capability.

R13 Experience quality metadata is separate from immutable approved Experience
text. Feedback must bind an approved Experience to an opaque Run, Challenge,
outcome, and optional Evidence IDs. Quality updates require an explicit
feedback action, remain auditable and idempotent, and never rewrite Skills or
promote Experience into current-challenge Intelligence.

R14 Local UI is an explicitly approved Presentation Layer phase. It may expose
complete challenge-local projections and call existing layer coordinators, but
it does not gain Tool, policy, approval, Runtime, or filesystem authority.
R14.1 provides loopback-only challenge intake and catalog views. R14.2 may call
a Runtime-owned supervised-run coordinator for start, session-level
pre-authorization, safe abort, and typed checkpoint resume. That coordinator
must construct `AgentRuntime` through the existing integration boundary; every
action still passes through ToolRuntime, PolicyEngine, ApprovalManager, audit,
and workspace containment, with high-risk denial and stop controls preserved.
R14.3 may expose read-only, challenge-local Intelligence, Web, artifact,
Completion report, and writeup projections, including recorded Flag values,
evidence, and paths. R14.4 may call the existing Experience candidate catalog
for explicit approve or reject decisions; candidate generation never writes
global Experience, approval alone may add sanitized memory, and rejection has
no global side effect.

Browser input must pass through existing Challenge Intake validation and
contained staging. Browser responses may include all values recorded for the
current challenge, including credentials, cookies, headers, Flag candidates,
and complete paths, because R14 is an explicitly authorized loopback operator
view. They must not include `config.json`, live raw Tool arguments or payloads,
Planner reasoning streams, audit logs, private checkpoints, or Tool authority.
The UI must not parse CLI output or create a second execution path.

The R10.2 experiment path integrates R6 reasoning state with controlled
execution and a bounded autonomous research loop, but never replaces the
execution boundary:

```text
Planner -> optional experiment_action
  -> ExperimentOrchestrator prepares Hypothesis + Experiment state
  -> ToolRuntime / PolicyEngine / ApprovalManager
  -> Observation with stable provenance
  -> EvidenceFactory (Artifact reference required)
  -> ExperimentEvaluator (SUPPORTED / CONTRADICTED / INCONCLUSIVE)
  -> Intelligence and bounded Domain feedback
  -> Research Context + multi-source Hypothesis candidates
  -> deterministic priority with failure penalties and Experience influence
  -> experiment_runtime.json + bounded ExperimentContextBuilder
  -> next Planner decision
```

The R7 experience path is separate from the per-run checkpoint:

```text
Completed Run / Intelligence / Experiments / Evidence
  -> rule-driven ExperienceExtractor
  -> sanitized ExperienceRecord
  -> global ExperienceStore
  -> deterministic ExperienceRetriever
  -> bounded next-challenge Planner context
```

The R8.6 completion path runs only after a challenge run has been bound:

```text
ChallengeManifest + RunState + Intelligence + Experiments + Evidence + Artifacts
  -> CompletionCollector (read-only)
  -> report.md + writeup.md + lessons.md
  -> sanitized experience_candidates.json (PENDING)
  -> explicit approve or reject
  -> approved candidate only -> global ExperienceStore
```

## Architectural Boundaries

### Completion: How a Finished Challenge Becomes Reviewable Knowledge

Completion reads persisted challenge state after a run. It may summarize only
recorded findings, experiments, evidence, artifact metadata, and run status.
It must not invent recon, exploitation, solution, or answer steps; call an LLM
to fill gaps; modify IntelligenceState; or treat evidence as a conclusion.
Completion output remains private per-challenge data.

Experience candidates are a separate, sanitized projection with `PENDING`,
`APPROVED`, or `REJECTED` review status. Generation never writes global
Experience memory. Only an explicit approval command may convert a candidate
into a global `ExperienceRecord`; rejection has no global side effect. Candidate
content must reject password, token, cookie, secret, flag, and credential data.

### Experience: What the Agent May Reuse Across Challenges

Experience answers what generic pattern, strategy, lesson, or failure was seen
in a past run. Intelligence answers what is known about the current challenge.
Never merge Experience into `IntelligenceState` or a per-run checkpoint.
Experience extraction must not copy credentials, flags, secrets, private target
data, payloads, or challenge answers. R7 extraction is rule-driven and uses no
LLM, embedding, vector search, graph database, model update, or Skill rewrite.
Retrieval is bounded context only and grants no execution authority.

### Experiment: How the Agent Tests a Hypothesis

The Experiment Layer owns hypothesis status, proposed test goals and expected
results, observed actual results, evidence provenance, and bounded Planner
context. Its managers do not call Tools. `ExperimentExecutor` records lifecycle
around execution already performed through ToolRuntime; it is not an alternate
execution backend. Evidence records observations and artifact links, never an
automatic conclusion. `ExperimentOrchestrator` and
`AutonomousExperimentLoop` have no Executor or Tool backend; AgentRuntime
supplies observations from the ordinary controlled path. R10.2 may mark a
Hypothesis `SUPPORTED`, reject a contradicted Hypothesis with bound Evidence,
or keep it OPEN with a follow-up suggestion. It never promotes `SUPPORTED` to
`CONFIRMED`, submits a flag, modifies a Skill, writes global Experience,
selects approval, or expands target scope.

Research candidates may come from Analyzer suggestions, current Intelligence,
declarative Domain phase context, or bounded sanitized Experience retrieval.
Their source, priority, Artifact provenance, Experience influence, score
reasons, and decision history must remain checkpointed and bounded. A ranked
experiment goal is reasoning context for the Planner, not permission or a Tool
call. Domain Runtime may record bounded evaluation feedback but must remain
Tool-decoupled. Experience may influence strategy but remains separate from
current-challenge Intelligence and must not be written by the experiment loop.

### Web Intelligence: How the Agent Understands a Web Challenge

Web Intelligence owns passive structure extraction, same-origin endpoint and
parameter mapping, technology indicators, and response comparison. HTML
analysis may parse forms, links, scripts, and comments but must never execute
JavaScript. Technology entries are evidence, not vulnerability claims.
Response differences may create a Finding and propose an OPEN hypothesis; they
must never confirm a vulnerability or execute an experiment automatically.

The Web attack surface supplied to the Planner must be bounded. Endpoint
findings belong to the current challenge IntelligenceState and retain artifact
provenance. Web Intelligence must never become a crawler, scanner, browser
automation layer, payload database, or exploit engine.

### Web Research: How Web Evidence Drives the Next Experiment

R11 Web Research owns the evidence-backed application model, masked session
lifecycle, Web experiment taxonomy, structured Web evidence projection, and
flag-candidate verification state. The model may relate endpoints,
parameters, authentication state, sessions, technologies, response behavior,
and artifact provenance. It must remain bounded and checkpoint-safe.

Web Research can recommend `ENDPOINT_ANALYSIS`, `PARAMETER_BEHAVIOR`,
`AUTHENTICATION_ANALYSIS`, `RESPONSE_COMPARISON`, `STATE_TRANSITION`,
`INPUT_BEHAVIOR_ANALYSIS`, `AUTHORIZATION_ANALYSIS`,
`FILE_PROCESSING_ANALYSIS`, `PARSER_BEHAVIOR_ANALYSIS`, or
`BUSINESS_LOGIC_ANALYSIS` goals.
These definitions contain no Tool name, payload, request, or execution
authority. Actual requests still follow ToolRuntime, PolicyEngine,
ApprovalManager, workspace, and exact local-origin controls. A flag candidate
requires Artifact evidence and explicit confirmation; the private local
Completion report may retain the confirmed candidate value alongside its
evidence and paths for operator review, while Planner context and global
Experience remain sanitized. Web research does not authorize
crawling, scanning, browser automation, payload generation, exploitation, or
public-target autonomy.

R12 may model parameter semantics, response formats, error patterns, access
states, user-controlled inputs, and application-state transitions only as
bounded evidence-oriented context. Name- or pattern-based classification is a
heuristic, not a vulnerability claim. Completion may extract sanitized Web
lessons, including failed experiments, but Global Experience still requires
explicit candidate approval.

### Runtime: How the Agent Operates

Runtime owns:

- The agent lifecycle and execution loop.
- State transitions and phase management.
- Planning and observation contracts.
- Coordination between domain, intelligence, skill, and execution layers.

Runtime does not own vulnerability knowledge, payloads, exploit scripts, or
direct tool execution. It must never call a tool backend by bypassing
ToolRuntime.

### Skill: How the Agent Thinks About a Domain

Skills own:

- CTF and security-domain knowledge.
- Analysis strategies.
- Heuristics and decision guidance.
- Reusable, non-executable reasoning instructions.

Skills must not contain shell commands, executable exploit scripts, live
network requests, or any mechanism that bypasses execution controls. Text that
describes a technique must remain reasoning material, not a hidden tool.

### Tool: What the Agent Can Execute

Tools provide explicit, typed capabilities such as:

- HTTP requests.
- Passive HTML parsing and captured-response comparison.
- File operations.
- Controlled Python execution.
- Future debugger and domain-specific operations.

Every tool action, including actions introduced in the future, must follow:

```text
Agent decision
  -> ToolRuntime
  -> PolicyEngine
  -> ApprovalManager
  -> Tool backend
  -> normalized Observation
```

No planner, skill, domain runtime, prompt, adapter, or MCP connection may call a
tool backend directly. Tools must validate inputs, preserve workspace
containment, expose meaningful risk metadata, and produce auditable results.

### MCP: How Future Tools Connect

MCP is a future tool connection protocol at the Environment/Execution boundary.
It may expose external capabilities through first-class Tool adapters, but it
does not expand authorization and must remain behind ToolRuntime, PolicyEngine,
and ApprovalManager.

MCP is not the agent brain, a runtime replacement, or a skill replacement. An
MCP server's availability is not permission to use it.

### Intelligence: What the Agent May Claim to Know

- Facts require evidence and provenance.
- Findings record meaningful observations and their context.
- Uncertain explanations remain hypotheses until supported.
- Artifacts must be associated with the action or observation that produced
  them.
- Checkpoints must preserve enough structured state to audit and resume a run.

Do not turn model speculation into facts or discard contrary evidence to make a
plan appear successful.

## Authorization and Security Boundary

All CTF activity must be:

```text
Authorized
  +
Scoped
  +
Controlled
  +
Auditable
```

- **Authorized:** the target and activity are explicitly permitted.
- **Scoped:** hosts, services, files, credentials, time windows, and actions stay
  within the granted challenge boundary.
- **Controlled:** execution is mediated by ToolRuntime, policy, approval, and
  workspace isolation.
- **Auditable:** decisions, approvals, actions, observations, and produced
  artifacts remain traceable.

Prefer execution environments in this order:

1. Fake local challenge or fake tool.
2. Local lab.
3. Local Docker container.
4. Dedicated VM or sandbox.
5. Explicitly authorized CTF instance.

Public-network targets are **DENY by default**. A target being reachable, named
in challenge text, or supported by a tool does not establish authorization.
Unknown systems must never be scanned or probed. Any future capability that can
affect a target must have a narrow typed contract, safe defaults, policy rules,
action-level approval behavior, tests, and an audit path before integration.

The following are prohibited:

- Bypassing or weakening `PolicyEngine`, `ApprovalManager`, ToolRuntime, or
  workspace isolation.
- Executing tool-like behavior from a skill, prompt, domain runtime, or adapter.
- Broadening a user-provided scope by assumption.
- Adding hidden, unlogged, or unreviewable execution paths.
- Defaulting network execution to the public internet.
- Testing scanners, payloads, or exploits against unknown or unauthorized
  systems.
- Treating credentials, challenge secrets, or sensitive artifacts as ordinary
  source files.

R5 HTTP execution remains loopback-only by default. Input-bearing or stateful
requests require action-level approval. R8 Web analysis is limited to captured
workspace artifacts; its endpoint mapper filters external origins and its
manager has no execution capability. Do not add browser automation, Burp
integration, scanners, payload databases, exploit-chain generation, real
Pwn/Reverse execution, multi-agent behavior, or GUI behavior outside an
explicitly approved roadmap phase.

## Domain Roadmap

Completed foundation:

- R5 Web Runtime Foundation.
- R6 Experiment Loop and Evidence-Driven Reasoning.
- R7 Experience Memory Foundation.
- R8 Web Intelligence Upgrade.
- R8.5 Challenge Intake and Experience Pipeline.
- R8.6 Challenge Completion and Experience Consolidation Pipeline.
- R9.1 Autonomous Execution Boundary.
- R9.2 Sandbox Runtime Foundation.
- R10.1 Experiment Runtime Integration.
- R10.2 Autonomous Experiment Loop.
- R11 Web Autonomous Research Foundation.
- R12 Web Capability Evolution.
- R13 Web Benchmark and Experience Evolution.

Completed UI phase:

- R14.1 Local UI Challenge Workbench.
- R14.2 Supervised Runs and Approval.
- R14.3 Safe Outcome and Completion Projections.
- R14.4 Reviewed Experience and Accessibility.

Planned domain progression:

1. Explicitly authorized real Web CTF validation.
2. Pwn Runtime.
3. Reverse Runtime.
4. Crypto Runtime.
5. Misc Runtime.

Each mature domain is composed of four distinct parts:

```text
Domain
+-- Runtime       lifecycle and domain state
+-- Skill         reasoning knowledge, strategies, and heuristics
+-- Tools         controlled executable capabilities
+-- Intelligence  domain evidence, findings, and hypotheses
```

A roadmap name does not authorize premature implementation or real-target
execution. Add each part through its owning layer and preserve the boundaries
defined above. Shared behavior belongs in shared contracts, not duplicated
inside domain implementations.

## Extension Rules

Every proposed feature must state:

- **Purpose:** the authorized CTF or learning problem it solves.
- **Architecture Layer:** the layer that owns it and the contracts it uses.
- **Security Boundary:** inputs, effects, scope, policy, approval, containment,
  and audit behavior.
- **Tests:** deterministic proof of contracts, safe defaults, and failure modes.
- **Demo:** a local, reproducible demonstration that does not require a public
  target.

Use this development order:

1. Define the contract and ownership boundary.
2. Implement the smallest useful capability.
3. Add deterministic tests with injected or fake dependencies.
4. Add a local demo.
5. Integrate a real environment only after its authorization and controls are
   explicit.

Do not begin by connecting an external tool or service. First define the
first-class Tool contract, policy behavior, approvals, observations, and test
substitute. Keep Planner, Tool backends, policy, intelligence storage, skills,
and domain lifecycle state as separate responsibilities.

## Development Workflow

Before implementation:

1. Read this document and the relevant architecture and roadmap documents.
2. Inspect the current contracts and tests; do not infer architecture from
   filenames alone.
3. Declare the feature's purpose, owning layer, security effects, and explicit
   non-goals.
4. Identify sensitive inputs and generated runtime data before reading or
   modifying files.

During implementation:

- Use Python 3.10+, four-space indentation, and UTF-8 text.
- Order imports as standard library, third-party, then local imports.
- Prefer typed dataclasses and explicit contracts at subsystem boundaries.
- Use dependency injection for external clients and nondeterministic behavior.
- Preserve action-level approval and workspace path validation.
- Make the safe path the default; rejected actions must fail closed.
- Keep documentation synchronized with implemented behavior.

Before handoff:

- Run targeted tests, then the appropriate local suite.
- Run `git diff --check`.
- Inspect `git status --short` and verify that only intended files changed.
- Report tests not run and any remaining limitation honestly.

Common development commands are:

```bash
source .venv/bin/activate
pytest -q
python main.py --help
python main.py tools list
python main.py intelligence show
python main.py domain list
python main.py skill list
python main.py runtime list
python main.py web status
python main.py web surface
python main.py web endpoints
python main.py web technologies
python main.py experiment list
python main.py experiment loop
python main.py experiment history
python main.py hypothesis list
python main.py evidence list
python main.py experience list
python main.py experience search sql
python -m pip check
```

## Validation Rules

Validation must progress through the least risky sufficient environment:

```text
Fake local challenge
  -> Local Docker challenge
  -> Explicitly authorized CTF instance
```

- Unit and integration tests must be deterministic and local-only by default.
- Tests and demos must use fake local tools unless a task explicitly authorizes
  another target.
- Never test against a public target without explicit authorization and scope.
- Negative tests must verify policy denial, approval requirements, input
  validation, and workspace containment.
- Domain runtime tests must prove lifecycle behavior without calling tools.
- Skill tests must prove routing and context behavior without executing skill
  content.
- Tool tests must use fake backends or isolated local fixtures before any real
  integration.
- Web analysis tests must use captured fake-local artifacts, prove external
  links are excluded from the attack surface, and keep evidence distinct from
  vulnerability conclusions.
- Experience tests must prove current-challenge intelligence isolation,
  checkpoint separation, bounded retrieval, and sensitive-data rejection.
- Completion tests must prove source-state immutability, evidence consistency,
  secret filtering, and approval-gated global Experience integration.

For every authorized real-challenge validation, preserve the following in the
approved, ignored runtime workspace:

- `RunState`.
- Produced artifacts and their provenance.
- `IntelligenceState`.
- A writeup or structured solution record.
- Lessons learned.

These records may contain private or sensitive challenge data. Do not commit
them or pass them directly into Experience memory. Only generic, sanitized,
rule-generated records may enter the ignored global Experience store.

## Long-term Learning Direction

The intended learning cycle is:

```text
Challenge Solving
  -> Writeup Generation
  -> Experience Extraction
  -> Knowledge Update
  -> Skill Improvement
```

R7 implements rule-driven `ExperienceRecord` extraction, a local JSON
`ExperienceStore`, deterministic retrieval, and bounded Planner context. It
does not automatically extract after every run or modify any other knowledge
asset.

The project may eventually introduce:

- A Knowledge Graph.
- A Pattern Library.
- Controlled Skill Evolution.

Knowledge evolution beyond the R7 foundation is **NOT IMPLEMENTED**. The
planned approach remains governed structured memory, not direct modification
of model weights. Future learning must preserve provenance, uncertainty,
authorization boundaries, reviewability, and rollback. Generated experience
must never silently rewrite skills or promote hypotheses to facts.

## Repository Rules

Never read, print, modify, or commit sensitive local data unless an explicit,
authorized task requires narrowly scoped handling. Never commit:

- `config.json` or `.env` files.
- API keys, tokens, passwords, or credentials.
- Runtime logs.
- Private checkpoints or unsanitized experience records.
- Challenge secrets, private flags, or user attachments.

Use `config_template.json` for public configuration examples and keep credential
fields empty. Store generated data only under designated ignored runtime
directories. Global experience belongs under the ignored `experiences/`
directory and never inside a single-run checkpoint.

Do not delete or rewrite the following merely to simplify a change:

- Architecture documentation.
- Tests.
- Historical validation reports.
- User runtime data or attachments.

Preserve unrelated work in a dirty worktree. Do not weaken security defaults as
part of an unrelated feature. Documentation describes implemented behavior;
roadmap or planned features must be labeled clearly as planned or not
implemented.

## Non-negotiable Review Questions

Before accepting any change, answer all of the following:

1. Is the purpose within authorized CTF research, security education, or
   defensive experimentation?
2. Which architecture layer owns it, and does it cross a forbidden boundary?
3. Can any action bypass ToolRuntime, PolicyEngine, ApprovalManager, or workspace
   isolation?
4. Are claims evidence-backed and are uncertain claims kept as hypotheses?
5. Are the defaults local, contained, least-privileged, and deny-by-default?
6. Are tests deterministic and is the demo local?
7. Could the change expose credentials, challenge secrets, private checkpoints,
   logs, or attachments?
8. Are documentation, validation evidence, and the roadmap status accurate?

If any answer is unsafe or unclear, stop integration and resolve the governance
or design issue first.
