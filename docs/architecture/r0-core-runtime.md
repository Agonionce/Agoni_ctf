# Agonionce R0 Core Runtime

## Goal

R0 establishes a small typed runtime with bounded execution and deterministic
tests. It does not implement Workspace, ArtifactStore, ToolPolicy, Browser,
Pwn, Reverse, Skill Router, or multi-agent orchestration.

## Architecture

```text
ChallengeSpec
    ↓
RunState / RunBudget
    ↓
AgentRuntime
    ├── Planner → ActionProposal → ToolCall[]
    ├── Executor → ToolResult[]
    ├── Observation
    ├── Analyzer → AnalysisResult / FlagCandidate[]
    └── TerminationController → RunStatus
```

The authoritative runtime state is `RunState.steps`. Challenge knowledge is
maintained separately by the R2 `IntelligenceState` layer.

## Contracts

`agent/runtime/contracts.py` defines `ChallengeSpec`, `RunState`, `RunBudget`,
`RunStatus`, `ActionProposal`, `ToolCall`, `ToolResult`, `Observation`,
`AnalysisResult`, `FlagCandidate`, `StepRecord`, and termination contracts.

## Runtime Flow

Each step follows:

```text
budget check
→ bounded Planner JSON attempts
→ ActionProposal validation
→ duplicate-action check
→ R1 ToolRuntime policy and action-level approval
→ Executor
→ Observation
→ Analyzer
→ StepRecord / counters
→ Flag confirmation or TerminationController
```

Planner and Analyzer use explicit JSON fields and typed contracts.

## Budget Defaults

```text
max_steps=100
max_runtime=7200
max_planner_retries=8
max_parser_retries=6
max_consecutive_failures=12
max_duplicate_actions=6
max_llm_calls=250
```

The runtime pauses its elapsed-time clock while manual approval is waiting.

## Current Boundary

The CLI Workflow constructs `AgentRuntime`. Execution routes through R1
`ToolRuntime`, `PolicyEngine`, and `ApprovalManager`; observations feed the R2
`KnowledgeUpdater`. R9.1 later adds a constrained `autonomous_local` policy
profile; this R0 document does not itself grant automatic Tool execution.

## Explicit Non-Goals

- no real API call in R0 tests;
- no network target or real CTF execution;
- no new Shell sandbox or policy engine;
- no Workspace, attachments, or artifacts;
- no rich Memory facts or hypotheses;
- no Skill Router or vector retrieval;
- no multi-agent framework.

## Deterministic Demo

`tests/integration/test_minimal_agent_runtime.py` uses a Fake Planner, Fake
Executor, and Fake Analyzer to produce and confirm:

```text
FLAG{LOCAL_AGENT_LOOP_OK}
```

## Known Remaining Risks

R0 alone does not provide an operating-system sandbox. R1 supplies application-
level workspace and policy controls, while R2 supplies structured knowledge.
Web, Pwn, and Reverse runtimes remain future work and must preserve the current
authorization boundary.
