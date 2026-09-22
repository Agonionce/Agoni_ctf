# Agonionce R4 — Domain Runtime Framework

R4 adds declarative lifecycle organization for each CTF domain. It answers
"when should the current investigation focus change?" while R3 Skills answer
"how should the Agent reason?" and R1 Tools remain the only execution path.

R4 contains no HTTP client, browser, binary inspection tool, debugger,
decompiler, exploit helper, MCP connection, remote target, or automatic
submission behavior.

## Architecture

```text
ChallengeSpec + artifact metadata
  ↓
R3 SkillRouter → DomainSelection / SkillContext
  ↓
DomainRuntimeManager
  ↓
DomainRuntime → DomainRuntimeState → PhaseDefinition
  ↓
DomainRuntimeContextBuilder + filtered R2 Intelligence
  ↓
Planner optional domain_runtime_context
```

`AgentRuntime`, `ActionProposal`, ToolRuntime, PolicyEngine, and approval
contracts remain unchanged. `JsonPlanner` receives the R4 context through an
optional provider, preserving `plan(challenge, state, tool_schemas)`.
`DomainRuntimeAnalyzer` decorates the existing Analyzer and routes only its
successful bounded summary to the manager; it does not infer phase completion.

## Runtime contract

`DomainRuntime` exposes:

- `phases()` for its immutable phase graph;
- `initialize()` for new or restored state;
- `next_phase()` for one validated explicit transition;
- `handle_observation()` for a bounded summary and optional explicit advance;
- `generate_context()` for the Planner-facing phase description.

No phase executes code. Each `PhaseDefinition` contains only a name, goal,
expected observations, allowed Skills, and declared next phases. Invalid or
skipped transitions are rejected.

## Runtime state

`DomainRuntimeState` complements rather than duplicates R0 and R2 state:

```text
RunState              orchestration and step history
DomainRuntimeState    domain, phase, phase history, small declared metadata
IntelligenceState     facts, hypotheses, findings, failures, questions
```

The domain state retains a challenge ID, current phase, transition history,
bounded last-observation summary, observation count, and small metadata copied
from `ChallengeSpec`. Pwn metadata has explicit `architecture` and
`binary_metadata` slots but performs no inspection.

## Registered runtimes and phases

```text
web      RECON → ANALYSIS → EXPLOITATION → VERIFY
pwn      TRIAGE → PROTECTION_ANALYSIS → VULNERABILITY_ANALYSIS
         → EXPLOITATION → VERIFY
reverse  TRIAGE → STATIC_ANALYSIS → DYNAMIC_ANALYSIS
         → ALGORITHM_RECOVERY
crypto   CLASSIFICATION → ANALYSIS → SOLVING → VERIFY
misc     ORIENTATION → ANALYSIS → VERIFY
```

`misc` preserves the R3 fallback path. `DomainRuntimeManager` owns runtime
registration, selection, initialization, transitions, and observation routing.
It never calls a Tool.

## Context and checkpoint

`DomainRuntimeContextBuilder` combines the challenge identity, current phase,
selected R3 skill context, and capped relevant R2 intelligence. Credential
collections are excluded. The Planner receives this separately from the R2
intelligence and R3 skill contexts.

New checkpoints add an optional `domain_runtime.json`:

```text
checkpoint/
├── run.json
├── intelligence.json
├── artifacts.json
├── experiments.json
└── domain_runtime.json
```

Older three-file checkpoints remain loadable. R4 resumes the persisted domain
and phase instead of reinitializing the lifecycle. R6 writes
`experiments.json`; it is independent of the optional domain runtime file.

## Configuration and CLI

`runtime.default_domain` defaults to `auto`; missing configuration preserves
R3 domain selection. Read-only inspection is available through:

```bash
python main.py runtime list
python main.py runtime current
```

## Safety boundary

- Runtime describes lifecycle; it does not decide vulnerability mechanics.
- Skill provides reasoning; it does not execute.
- Tool remains the only action abstraction and stays behind R1 policy.
- Intelligence remains evidence state and is not copied into lifecycle state.
- No network, real Shell, real CTF target, MCP, or domain tool is used by R4.
