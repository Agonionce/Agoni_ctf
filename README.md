# Agonionce

[![CI](https://github.com/Agonionce/Agoni_ctf/actions/workflows/ci.yml/badge.svg)](https://github.com/Agonionce/Agoni_ctf/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)

Agonionce is an autonomous CTF agent framework designed for authorized
security research, CTF competitions and local challenge environments.

It combines bounded autonomous reasoning, policy-controlled tool execution,
durable challenge intelligence, hypothesis-driven experiments, cross-run
experience, domain skills, and declarative domain lifecycles behind explicit
safety and approval boundaries.

## Introduction

Agonionce turns a challenge description into a structured solving loop:

```text
Challenge
  ↓
Planner → ActionProposal
  ↓
Policy → Approval → ToolRuntime
  ↓
Observation → Analyzer
  ↓
IntelligenceState → next Planner context
```

The framework separates runtime state, executable actions, and CTF knowledge.
Facts remain distinct from hypotheses, failed approaches are retained, and
generated artifacts stay linked to the steps that produced them.

## Engineering Highlights

- **Governed execution:** every action flows through typed Tool contracts,
  policy evaluation, approval, workspace containment, and audit records.
- **Evidence-driven research:** observations, findings, hypotheses,
  experiments, and conclusions retain explicit provenance instead of being
  collapsed into an opaque chat history.
- **Recoverable state:** checkpoints preserve Runtime, Intelligence, Artifact,
  Domain, Experiment, and research state for deterministic resume.
- **Reviewed learning:** reusable experience is sanitized, bounded, and added
  to global memory only after an explicit approval step.
- **Local operator UI:** a loopback-only React workbench supports challenge
  intake, supervised runs, results, completion reports, and experience review.
- **Reproducible validation:** the repository includes deterministic unit and
  local integration tests plus fake-local demonstrations that contact no
  public target.

## Architecture

```text
Agonionce
├── Core Runtime
│   ├── Planner / Executor / Analyzer
│   ├── RunState / RunBudget
│   └── TerminationController
├── Controlled Execution
│   ├── ToolRegistry / ToolRuntime
│   ├── PolicyEngine / ApprovalManager
│   └── Workspace / ArtifactStore
├── Intelligence State
│   ├── Facts / Hypotheses / Findings
│   ├── Failed Attempts / Open Questions
│   └── JSON Checkpoint / Retrieval
├── Domain Intelligence
│   ├── Web / Pwn / Reverse / Crypto / Misc
│   ├── Deterministic SkillRouter
│   └── Validated SkillLoader / bounded Planner context
├── Domain Runtime Framework
│   ├── DomainRuntimeManager
│   ├── Declarative phases / DomainRuntimeState
│   └── Runtime context / checkpoint persistence
├── Web Runtime Foundation
│   ├── Loopback-only HTTPRequestTool
│   ├── Request / Response / Session artifacts
│   └── WebRuntimeState / deterministic response facts
├── Web Intelligence
│   ├── HTMLAnalyzer / EndpointMapper / TechnologyDetector
│   ├── ResponseBehaviorAnalyzer / WebAttackSurface
│   └── WebIntelligenceTool / bounded Planner context
├── Experiment Loop
│   ├── Hypothesis / Experiment / Evidence lifecycles
│   └── Evidence-backed closure and checkpoint restore
├── Experience Memory
│   ├── Rule-driven extraction / global JSON store
│   └── Deterministic bounded retrieval
├── MCP Foundation
│   ├── Explicit local stdio server registry / health
│   ├── MCP schema-to-Tool adapters / provenance
│   └── ToolRuntime / Policy / Artifact integration
└── Challenge Runtime
    └── Platform input and flag submission adapters
```

Architecture details are documented under [docs/architecture](docs/architecture/).

## Current Status

- R0 Core Runtime — complete
- R1 Controlled Execution Environment — complete
- R2 CTF Intelligence State — complete
- R2.5 Project Identity Cleanup — complete
- R3 Domain Intelligence Framework — complete
- R4 Domain Runtime Framework — complete
- R5 Web Runtime Foundation — complete
- R5.1 Engineering Governance — complete
- R6 Experiment Loop and Evidence-Driven Reasoning — complete
- R7 Experience Memory Foundation — complete
- R8 Web Intelligence Upgrade — complete
- R8.5 Challenge Intake and Run Binding — complete
- R8.6 Completion and Experience Consolidation — complete
- R9.1 Autonomous Execution Boundary — complete
- R9.2 Sandbox Runtime Foundation — complete
- R10.1 Experiment Runtime Integration — complete
- R10.2 Autonomous Experiment Loop — complete
- R11 Web Autonomous Research Foundation — complete
- R12 Web Capability Evolution — complete
- R13 Web Benchmark and Experience Evolution — complete
- R14 Local UI Challenge Workbench (R14.1–R14.4) — complete
- R14 MCP Foundation — complete (local stdio only)

The CLI defaults remain governed and manual. The local workbench offers a
session-level pre-authorization mode for the current, explicitly authorized
challenge: policy-allowed in-scope actions proceed automatically while
ToolRuntime, PolicyEngine, ApprovalManager, audit records, workspace
containment, high-risk denial, and safe-stop controls remain active. R5 HTTP
execution is additionally restricted to the loopback origin declared by the
current challenge.

## Safety Boundary

Agonionce is intended only for:

- authorized CTF competitions;
- coursework and training labs;
- local challenge environments;
- explicitly authorized security research.

Do not use Agonionce for unauthorized scanning, exploitation, access attempts,
or testing against public or production systems without explicit permission.
R1 policy and workspace controls are application-level boundaries, not an
operating-system sandbox.

R8 passively analyzes captured local Web artifacts. It extracts forms, links,
scripts, comments, same-origin endpoints and parameters, technology indicators,
and response differences. These observations may create findings and OPEN
hypotheses, but do not confirm vulnerabilities or execute experiments.

## Roadmap

- Authorized real Web research validation after explicit scope review
- Pwn Runtime
- Reverse Runtime
- Crypto Runtime
- Misc Runtime

See the [project roadmap](docs/roadmap/roadmap.md) for scope boundaries.

## Development

Requirements:

- Python 3.10+
- Git
- Node.js 20.19+ or 22.12+ (only for building the local UI)

Create an isolated environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Create local configuration without committing credentials:

```bash
cp config_template.json config.json
```

Set the OpenAI-compatible endpoint, model, and API credential in the ignored
`config.json` file. Never place credentials in source, documentation, logs, or
commits.

Inspect the CLI and current boundaries:

```bash
python main.py --help
python main.py challenge create
python main.py challenge list
python main.py tools list
python main.py policy check
python main.py intelligence show
python main.py domain list
python main.py skill list
python main.py runtime list
python main.py runtime current
python main.py web status
python main.py web surface
python main.py web endpoints
python main.py web technologies
python main.py hypothesis list
python main.py experiment list
python main.py experience list
python main.py mcp list
python main.py mcp status
python main.py mcp tools
```

Build and open the loopback-only challenge workbench:

```bash
cd webui/frontend
npm install
npm run build
cd ../..
python main.py ui start
```

The browser interface supports creating and naming an authorized challenge,
writing its Markdown description, uploading attachments or source files,
starting or resuming an automatically authorized local run, reviewing the one
Flag result (or an explicit not-found result), and inspecting the complete
recorded evidence and analysis-material paths. The Presentation Layer never
executes a Tool, submits a flag, or displays internal reasoning or live logs;
the Runtime continues to own execution, policy, audit, and containment.

Import and start an authorized challenge from the CLI in manual mode:

```bash
python main.py challenge create
python main.py solve --challenge <challenge-id> --manual --no-resume
```

Run validation:

```bash
pytest -q
cd webui/frontend && npm test && npm run typecheck && npm run build && cd ../..
python -m pip check
python -m compileall -q agent cli ctf_platform skill skills utils tests main.py config.py
```

Run the R8 authorized-local Flask demo:

```bash
python -m demos.r8_local_web_intelligence_loop
```

It prints `LOCAL_WEB_INTELLIGENCE_LOOP_OK` after passive mapping, hypothesis,
controlled experiment, evidence, and verification complete.

Run the R8.5 fake-local intake demo:

```bash
python -m demos.r85_local_challenge_intake
```

It prints `LOCAL_CHALLENGE_INTAKE_OK` after contained import, workspace
bootstrap, artifact binding, and writeup-template creation.

Run the R14 local UI intake contract demo:

```bash
python -m demos.r14_local_ui_workbench
```

It prints `LOCAL_UI_WORKBENCH_OK` after an authorized fake challenge is created
and projected without exposing workspace paths or contacting a target.

Run the supervised workbench contract demo:

```bash
python -m demos.r14_supervised_workbench
```

It prints `LOCAL_UI_SUPERVISED_WORKBENCH_OK` after the fake-local run,
completion projection, and explicit Experience review complete without
invoking a Tool or contacting a target.

Run the R14 local MCP foundation demo:

```bash
python -m demos.r14_mcp_foundation
```

It prints `LOCAL_MCP_FOUNDATION_OK` after a discovered local stdio MCP Tool
passes through ToolRuntime, Policy, ArtifactStore, Observation, and the
deterministic AgentRuntime loop. See
[R14 MCP Foundation](docs/development/r14-mcp-foundation.md) for configuration,
capability declarations, CLI inspection, and the external-tool boundary.

More detail is available in the
[development guide](docs/development/getting-started.md).

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
