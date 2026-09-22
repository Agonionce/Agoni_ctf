# Agonionce R1 — Controlled Execution Environment

R1 places a small, explicit safety boundary between R0 planning and any local
execution backend. It is for authorized CTF challenges, coursework, local
labs, and security research environments only.

## Runtime path

```text
AgentRuntime
  ↓
Planner → ActionProposal
  ↓
ToolRuntimeExecutor
  ↓
ToolRuntime → PolicyEngine → ApprovalManager
  ↓
Registered Tool
  ↓
ToolResult → ArtifactStore → Observation
```

`AgentRuntime` owns step state. Before executing a proposal, it offers an
optional `prepare(state, step_id, proposal)` hook. The R1 executor uses that
hook to create a workspace-bound `ExecutionContext`; existing fake executors do
not need to implement it.

## Tool surface

`ToolRegistry` owns the only Planner-visible tool schemas. R1 deliberately
registers only:

- `file`: read-only metadata inspection inside the current workspace.
- `python`: execute a workspace-local Python script after approval.
- `bash`: compatibility backend for one policy-reviewed workspace command.

Tools return `ToolExecutionOutput`; `ToolRuntime` converts that into the R0
`ToolResult`, attaching policy decision, execution context, artifact
references, and an append-only JSONL audit entry.

R5 extends the registered surface with `http_request`. It remains behind the
same ToolRuntime and action-level policy boundary; the backend is loopback-only
and emits request, response, and session artifacts.

## Policy and approval

`PolicyEngine` is independent of both Planner and Executor. Its decisions are
`ALLOW`, `REQUIRE_APPROVAL`, or `DENY`.

- Workspace-contained low-risk file inspection is allowed.
- Medium-risk actions such as Python execution, writes, unknown tools, and
  commands such as `curl` require one explicit action-level approval.
- High-risk commands (`rm`, `sudo`, `chmod`, `kill`, and related commands),
  malformed paths, and paths outside the workspace are denied.

The default config is `execution.mode = "manual"` with a `safe` policy. R1 did
not originally enable `--auto`. R9.1 supersedes that historical CLI limitation
with a constrained `autonomous_local` profile while preserving ToolRuntime,
policy, approval, workspace, and audit boundaries. `ApprovalManager` owns
pending, approved, and rejected states; the CLI only presents a request and
returns the user decision.

## Workspace and artifacts

`WorkspaceManager` creates a path per challenge:

```text
workspace/<challenge-id>/
  input/
  work/
  output/
  logs/
```

All path-bearing tool arguments are resolved inside this root. `ArtifactStore`
records generated local artifacts in `logs/artifacts.json` with an ID, relative
path, creator, timestamp, source step, and type. Tool lifecycle records are
appended to `logs/tool-audit.jsonl`; each retains caller, timestamps,
objective/reasoning, arguments, policy decision, normalized output (including
error/exit information), and artifact references.

## Deliberate limits

R1 is an authorization and audit boundary, not an operating-system sandbox.
The subprocess-backed Python and Bash tools remain deliberately small and must
only be approved for authorized local challenge workspaces. Web runtime,
browser automation, pwn/reverse runtimes, memory intelligence, multi-agent
coordination, and GUI work are out of scope until later releases.
