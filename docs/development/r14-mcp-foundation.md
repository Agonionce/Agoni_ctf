# Agonionce R14 — MCP Foundation

## Result

R14 adds a local-first, general-purpose MCP integration layer. MCP is an
external capability transport for the existing Tool layer; it is not an Agent
Runtime, Planner, policy engine, or direct execution path.

```text
Planner / Experiment Runtime
  -> ToolCall
  -> ToolRuntime
  -> PolicyEngine / ApprovalManager
  -> MCPToolAdapter
  -> local stdio MCP client
  -> explicitly configured local MCP server
  -> ToolResult / Artifact / Observation / Evidence
```

Every discovered MCP capability becomes an ordinary registered `Tool`. The
Planner sees the same JSON Schema shape it sees for built-in Tools. The
execution boundary remains unchanged.

## Ownership and boundaries

`agent/mcp/` owns server configuration contracts, the local stdio client,
discovery, schema adaptation, result normalization, server health, and MCP
provenance. It does not own Tool execution policy, approval decisions,
workspace access, Intelligence conclusions, Evidence evaluation, or checkpoint
format.

R14 supports only an explicitly configured local `stdio` server. There is no
HTTP/SSE transport, public endpoint, implicit server discovery, shell command
string, browser automation, scanner, or software-specific integration.

A server is disabled unless `enabled: true` is explicitly configured. Starting
an enabled local process only performs the MCP handshake and `tools/list` when
discovering its schema; it never invokes an exposed MCP Tool. A discovered tool
is still not authorized to run until its ordinary `ToolRuntime` policy and
approval path allow the specific `ToolCall`.

## Server registry and configuration

The ignored local `config.json` can include an `mcp` object. Commands are
provided as an argv program plus argv arguments; no shell is involved. R14
does not accept environment-variable configuration, so the safe CLI projection
does not expose secret values.

```json
{
  "mcp": {
    "servers": [
      {
        "id": "local_fixture",
        "transport": "stdio",
        "command": "/path/to/python",
        "args": ["/absolute/path/to/server.py"],
        "enabled": true,
        "timeout_seconds": 10,
        "tool_capabilities": {
          "read_record": {
            "read_only": true,
            "state_changing": false,
            "network": false,
            "filesystem": false,
            "execution": false,
            "external_application": false
          }
        }
      }
    ]
  }
}
```

Capability effects are a locally configured policy declaration, not a claim
trusted from the MCP server. An undeclared tool defaults to high risk,
state-changing, and external-application interaction. A `read_only` capability
must declare no side effects. Autonomous-local execution is disabled unless a
capability is explicitly read-only and configured for it.

The registry keeps a bounded status projection:

- server identity, enabled state, and `stdio` transport;
- `DISABLED`, `UNKNOWN`, `READY`, or `ERROR` health;
- discovered tool schemas and server name/version;
- only a compact latest-call status, not raw arguments or result values.

## MCP Core and Tool adapter

`StdioMCPClient` performs the standard MCP foundation sequence:

1. start an explicitly configured argv process;
2. send `initialize` and `notifications/initialized`;
3. call `tools/list` to discover remote capabilities;
4. call `tools/call` only from the adapter after ToolRuntime authorization;
5. close the short-lived local session.

`MCPToolAdapterRegistry` converts every valid discovered descriptor into an
ordinary Tool named:

```text
mcp__<server-id>__<remote-tool-name>
```

The adapter retains the MCP server ID, remote tool name, transport, server
name/version, schema SHA-256, and locally declared capability profile as Tool
provenance. Invalid remote schemas are fail-closed: they are not registered and
the relevant server health becomes `ERROR`; built-in Tools remain available.

## Policy, approval, audit, and checkpoints

The adapter only implements `Tool.execute`; it never calls a backend outside
`ToolRuntime`.

- a declared effect-free read-only MCP Tool has `LOW` risk and follows the
  normal low-risk policy;
- state-changing, filesystem, execution, network, or external-application
  declarations require the existing approval path (and are never made
  autonomous by discovery);
- unknown remote tools default to high risk;
- ToolRuntime validates the converted remote JSON Schema before policy;
- its existing audit record contains redacted MCP provenance and a normal
  artifact reference;
- `ToolResult` and `Artifact` metadata are checkpointed through the existing
  RuntimeStepCheckpoint without a new persistence path.

## Artifact and Evidence flow

MCP content is normalized into a challenge-contained result artifact under:

```text
workspace/<challenge>/output/mcp/<server>-<tool>-step-<n>-<id>.json
```

The artifact retains the full normalized MCP result plus provenance. `stdout`
contains only a 4 KB text preview and result counts. The protocol accepts at
most 2 MB per response message and at most 2 MB per artifact; an over-limit
result becomes a normal, auditable Tool failure instead of overflowing planner
or audit context. This preserves the normal ArtifactStore → Observation →
Analyzer → Evidence route for later domain-specific adapters such as a Web
traffic response projection.

## CLI

All commands are read-only with respect to MCP-exposed Tools:

```bash
python main.py mcp list
python main.py mcp status
python main.py mcp tools
python main.py mcp tools <server>
python main.py mcp inspect <server>
```

`list` reads configuration only. `status`, `tools`, and `inspect` perform the
local handshake/discovery but never invoke a remote MCP Tool. Commands accept
`--config /path/to/config.json` for local development and never render the
configured executable command or any secret-bearing environment values. Server
error messages and latest-call status use the same credential/Flag redaction
rule before CLI rendering.

## Local fixture and demo

`demos/r14_mcp_fixture_server.py` is a deterministic local stdio MCP fixture.
It exposes echo, fixture reads, a calculation, an in-memory state-changing
fixture operation, and a bounded delay for timeout tests. It opens no socket,
starts no external software, and writes no files.

Run the full local path with:

```bash
python -m demos.r14_mcp_foundation
```

It prints:

```text
LOCAL_MCP_FOUNDATION_OK
```

The demo exercises a fake challenge through Planner → AgentRuntime →
ToolRuntime → MCP adapter → local fixture → ToolResult/Artifact/Observation.

## Validation

R14 tests cover configuration validation, discovery, schema conversion,
low-risk and approval-required policy paths, artifact and audit provenance,
remote errors, timeouts, checkpoint restore, CLI discovery, and a full
AgentRuntime integration path. All fixtures are local and deterministic.

## Remaining risks and R14.1 direction

R14 trusts an enabled local server command as an operator-selected integration
process. It does not sandbox that server, establish persistent stateful MCP
sessions, or support remote transports. A future external integration must add
its own typed capability profile, local authorization model, deterministic fake
fixture, output limits, policy tests, and evidence projection before it is made
available to a Planner.

Recommended R14.1 direction is a separately governed Burp integration that
begins with passive, captured-traffic retrieval from an explicitly selected
local Burp instance. It must not add crawling, live request replay, payload
generation, public-target access, or any bypass of ToolRuntime, PolicyEngine,
ApprovalManager, workspace containment, and audit.
