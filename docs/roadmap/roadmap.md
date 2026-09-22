# Agonionce Roadmap

## Completed foundations

- R0 — Core Runtime
- R1 — Controlled Execution Environment
- R2 — CTF Intelligence State and Persistent Reasoning
- R2.5 — Project Identity Cleanup and Repository Rebranding
- R3 — Domain Intelligence Framework
- R4 — Domain Runtime Framework
- R5 — Web Runtime Foundation
- R5.1 — Engineering Governance
- R6 — Experiment Loop and Evidence-Driven Reasoning
- R7 — Experience Memory Foundation

## Completed product phase

### R14 Local UI Foundation

R14 is approved as a phased, loopback-only Presentation Layer. R14.1 provides
the challenge catalog, Markdown intake, contained uploads, and challenge detail.
R14.2 adds supervised run milestones, action-level decisions, safe abort, and
typed resume through a Runtime-owned coordinator. R14.3 adds read-only safe
outcome and completion projections. R14.4 adds explicit Experience candidate
review and accessibility hardening. No phase exposes internal execution detail
or bypasses Runtime, ToolRuntime, PolicyEngine, or ApprovalManager.

### R14 MCP Foundation

R14 MCP Foundation adds only explicit local `stdio` MCP server configuration,
discovery, schema-to-Tool adaptation, provenance, result normalization, and
CLI health inspection. Every invocation remains behind ToolRuntime,
PolicyEngine, ApprovalManager, ArtifactStore, audit, and checkpointing.
Unknown MCP tools default to high risk. The phase introduces no remote
transport, scanner, crawler, browser automation, request replay, payload
generation, or public-target access.

## Future phases

### Domain Runtime Integrations

Workspace-contained binary inspection, exploit-development primitives, and
structured reverse-analysis adapters for authorized local or CTF targets.

### Experience Evolution

Governed pattern libraries and reviewed knowledge evolution may build on R7.
Automatic Skill rewriting, model training, graph databases, vector search, and
multi-agent experience roles remain out of scope until explicitly governed.

## Persistent constraints

- Explicit authorization is mandatory.
- Unknown behavior defaults to approval or denial.
- Tool execution remains auditable and workspace-scoped.
- Facts, hypotheses, failures, and artifacts keep source provenance.
- New runtimes must not weaken completed safety gates.
- Web requests remain target-scoped and policy-controlled.
