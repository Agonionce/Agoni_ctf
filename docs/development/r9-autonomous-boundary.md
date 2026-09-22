# Agonionce R9.1 — Autonomous Execution Boundary

## Result

R9.1 establishes the execution contract required for a safe autonomous local
CTF agent. It adds no scanner, exploit engine, payload knowledge, browser
automation, remote-target automation, or host sandbox. The new boundary makes
local autonomous decisions enforceable, typed, contained, recoverable, and
auditable before later sandbox work begins.

The controlled path is now:

```text
Planner
  -> ToolCall
  -> JSON Schema Validation
  -> Workspace Scope Validation
  -> PolicyEngine + Execution Mode
  -> ApprovalManager when required
  -> Tool backend
  -> ArtifactStore
  -> ToolResult + redacted audit
```

## Architecture

R9.1 remains inside existing ownership boundaries:

- `agent/workspace/path.py` owns workspace URI parsing, scope resolution, and
  containment.
- `agent/tools/validation.py` owns Tool argument JSON Schema validation.
- `ExecutionSettings` and `PolicyEngine` own mode parsing and action policy.
- `ToolRuntime` remains the only first-class Tool execution gateway.
- `agent/tools/workspace/` owns structured local file capabilities.
- `AgentRuntime` emits lifecycle checkpoints; it does not persist files
  directly.
- `RuntimeStepCheckpoint` owns atomic runtime/intelligence/checkpoint writes.

No Skill, Domain runtime, Planner prompt, analyzer, or challenge adapter gains
a direct execution path.

## Execution Modes

The `execution.mode` contract accepts exactly:

| Mode | Behavior |
| --- | --- |
| `manual` | Safe default. Policy-denied calls fail closed; approval-classified calls require the user resolver. Host Bash and Python always require approval. |
| `supervised` | Continuous reasoning may automatically use registered read-only low-risk Tools. Medium-risk, stateful, network-bearing, or host-process actions retain approval requirements. |
| `autonomous_local` | Only Tools carrying `autonomous_allowed=true` may run. Their own typed scope remains enforced. Bash and Python are denied, public targets are denied, and input-bearing HTTP still requires an approval that a non-interactive run does not invent. |

Example public configuration:

```json
{
  "execution": {
    "mode": "autonomous_local",
    "workspace_root": "workspace",
    "default_policy": "safe"
  }
}
```

Absent configuration remains `manual`. `python main.py solve --auto` selects
`autonomous_local` for that invocation; it does not grant remote authority or
enable host-process Tools.

## Workspace Contract

The canonical Planner/Tool path syntax is:

```text
workspace://input/file.txt
workspace://work/script.py
workspace://output/result.txt
```

The scopes have fixed meanings:

- `input`: imported challenge attachments and source; readable, not writable
  through the structured write Tool.
- `work`: challenge-local scratch and generated analysis files.
- `output`: durable Tool outputs and evidence artifacts.
- `logs`: internal only; not part of the public Tool URI surface.

`WorkspacePathResolver` parses the URI, rejects query/fragment ambiguity,
rejects `..`, follows filesystem resolution for containment checks, validates
the allowed scope, and only then returns a host `Path`. User-controlled paths
must not be joined by individual Tool implementations.

Challenge manifests retain portable root-relative paths on disk for backward
compatibility. Runtime metadata exposes those paths as canonical workspace
URIs and retains explicitly named legacy fields only for older consumers.
Legacy `input/...` and work-relative values remain accepted at the resolver
boundary during migration; new Planner actions should always emit workspace
URIs.

## Tool Security Model

Every registered Tool input schema is checked when the Tool is registered.
Every ToolCall argument object is validated with JSON Schema before policy is
evaluated. A failure produces a normalized ToolResult with:

```json
{
  "tool_error": {
    "code": "TOOL_ARGUMENT_SCHEMA_ERROR",
    "message": "...",
    "field_path": "$.path",
    "schema_path": "properties/path/type"
  }
}
```

Its policy decision is recorded as `NOT_EVALUATED`, proving the backend and
policy classification were not reached with malformed input.

R9.1 adds these structured Tools:

- `workspace_list`: bounded, non-recursive directory metadata.
- `workspace_read_text`: bounded UTF-8 reads.
- `workspace_read_bytes`: bounded binary fragments returned as base64 and a
  short hex preview.
- `workspace_write_text`: bounded writes to `work` or `output`; input is
  immutable and overwrite is explicit.
- `file_hash`: streaming SHA-256 calculation.
- `archive_list`: bounded ZIP/TAR member metadata with no extraction.

All six pass through ToolRuntime, PolicyEngine, ApprovalManager as applicable,
and ArtifactStore for generated files. Read limits and list limits bound
Planner context growth. Archive contents are never extracted or executed.

The legacy `file` Tool is retained for compatibility. `bash` and `python` are
also retained, but both declare `autonomous_allowed=false`. Bash now always
requires manual approval outside autonomous mode, and relative as well as
absolute path traversal is denied by policy.

## Autonomous Boundary

`autonomous_local` is a capability allowlist, not an approval bypass:

```text
autonomous_local
  +-- structured workspace Tools: permitted within declared scopes
  +-- passive Web intelligence: permitted on captured artifacts
  +-- HTTP: loopback + exact challenge declaration only
  +-- stateful/input-bearing HTTP: approval still required
  +-- Bash/Python: denied
  +-- public/unknown targets: denied
```

Tool availability does not establish authorization. HTTP policy continues to
require both loopback addressing and an exact target declared by the current
challenge. No R9.1 code relaxes the R5 public-network denial.

## Step Checkpoints

The checkpoint directory now includes `step.json`. The runtime atomically
updates the ordinary `run.json`, `intelligence.json`, `experiments.json`,
`artifacts.json`, and domain state before writing the latest intra-step stage:

```text
planner_proposal
  -> tool_approval
  -> tool_result
  -> analyzer_result
  -> experiment_update
  -> step_complete
```

`step.json` carries the proposal, accumulated approval events, Tool results,
Analyzer result, experiment/intelligence counts, and timestamps. On resume:

- a durable `tool_result` continues at Analyzer without re-executing the Tool;
- a durable `analyzer_result` applies its knowledge update once;
- a durable `experiment_update` records the step without reapplying the
  update;
- a completed step resumes from the ordinary RunState.

An interruption after host effects but before the Tool result is durable
cannot yet be proven idempotent. Autonomous R9.1 Tools are deliberately narrow
and local, but exactly-once external effects remain future work.

## Audit

Each Tool audit record now contains the required stable fields:

- `run_id`
- `step_id`
- `tool`
- `arguments_hash` (SHA-256 over canonical original arguments)
- `policy_result`
- `execution_mode`
- `timestamp`

Legacy audit fields remain for compatibility. Arguments, metadata, objective,
reasoning, stdout, stderr, and errors are recursively redacted for cookie,
token, password, credential, API-key, secret, and flag-shaped values before
they enter the JSONL audit. Runtime ToolResult/checkpoint data remains private
workspace state and must not be committed.

## Demo

Run the fake-local boundary demonstration:

```bash
python demos/r91_autonomous_boundary.py
```

It creates one temporary fake challenge, uses `workspace_list` and
`workspace_read_text` in `autonomous_local`, proves Bash is denied, opens no
network connection, and prints:

```text
LOCAL_AUTONOMOUS_BOUNDARY_OK
```

## Future Sandbox Plan

R9.1 classifies and blocks host-process execution in autonomous mode; it does
not sandbox Bash or Python. The next phase may introduce a disposable local
Docker/VM execution environment with:

- no network by default;
- explicit filesystem mounts;
- CPU, memory, PID, time, disk, and output limits;
- non-root execution, `no-new-privileges`, and syscall restrictions;
- one sandbox lifecycle per authorized challenge or experiment;
- ToolRuntime policy, approval, artifact, and audit integration outside the
  sandbox boundary.

Until that exists, Bash and Python remain manual/supervised host capabilities
and are never autonomous.

## Validation

Validated from the project virtual environment:

```text
pytest -q                         118 passed
python -m pip check              No broken requirements found
python -m compileall .            PASS
python demos/r91_autonomous_boundary.py
                                  LOCAL_AUTONOMOUS_BOUNDARY_OK
git diff --check                 PASS
python main.py --help            PASS
```

The host Anaconda environment has an unrelated pre-existing `zai-sdk` versus
`PyJWT` dependency conflict. It is not part of Agonionce requirements; the
project `.venv` is the authoritative validation environment and passes
dependency checking.

## Remaining Risks

- No Docker, VM, seccomp, or operating-system process isolation exists.
- Manual approval cannot turn a host shell into a strong sandbox.
- Checkpoints provide at-least-once recovery before a durable Tool result, not
  exactly-once external effects.
- HTTP session isolation and browser execution are not implemented.
- Remote target automation remains prohibited and unavailable.
- R9.1 adds no vulnerability knowledge, payload generation, or exploit
  capability.

R9.1 is ready for a future sandbox runtime only after all deterministic tests,
the local demo, dependency validation, compilation, and repository checks
pass.
