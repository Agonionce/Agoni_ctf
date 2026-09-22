# Agonionce R3 — Domain Intelligence Framework

R3 adds a deterministic knowledge-routing layer between challenge state and the
Planner. It does not add a Web, Pwn, Reverse, network, Shell, debugger, browser,
or exploit execution runtime.

## Architecture

```text
ChallengeSpec + artifact metadata
  ↓
SkillRouter
  ↓
DomainSelection
  ├── selected_domains
  ├── selected_skills
  └── confidence / rationale
  ↓
SkillLoader → validated Markdown knowledge
  ↓
SkillContextBuilder + relevant R2 intelligence
  ↓
Planner domain_context
```

R3 `SkillRouter` uses only local keyword rules. It makes no LLM, embedding,
vector, network, or Tool call. The default registry is ordered and bounded:

```text
web → pwn → reverse → crypto → misc
```

`misc` is the safe fallback when no stronger deterministic signal reaches the
selection threshold. Configuration may set `domain.default` to `auto` or one
registered domain.

## Contracts

`Domain` owns a name, description, deterministic `detect()` method, bounded
skill catalog, and validated `get_skill()` lookup. Concrete domains classify
metadata only; they do not execute domain operations.

`Skill` contains:

- name and domain;
- description, tags, and priority;
- knowledge;
- strategies;
- heuristics.

A Skill is reasoning guidance, never a Tool. It cannot execute a command,
access the network, or bypass R1 policy and approval.

## Skill assets and loading

Assets live under domain directories in `skills/`. Each Markdown file requires
YAML frontmatter (`name`, `domain`, `description`, `tags`, and `priority`) and
non-empty `Knowledge`, `Strategies`, and `Heuristics` sections. `SkillLoader`
recursively discovers assets, validates metadata, rejects duplicate names, and
exposes domain-filtered lookup.

The initial catalog is intentionally small:

- Web: `web_general`, `authentication`, `sql_injection`, `xss`, `ssrf`.
- Pwn: `binary_triage`, `memory_corruption`, `stack_overflow`, `ret2libc`.
- Reverse: `binary_analysis`, `static_analysis`, `dynamic_analysis`.
- Crypto: `encoding`, `classical_crypto`, `hash_analysis`.
- Misc: `misc_general`.

## Context boundary

`SkillContextBuilder` injects only selected skills. Per-skill guidance and R2
intelligence collections are capped, unrelated collections are omitted, and
credential values are not accepted into domain context. The Planner protocol
remains `plan(challenge, state, tool_schemas)`; `JsonPlanner` receives an
optional `domain_context_provider` through dependency injection.

## CLI

The read-only catalog commands are:

```bash
python main.py domain list
python main.py skill list
python main.py skill current
```

`skill current` routes the latest local checkpoint when one exists. These
commands do not execute a Tool or contact an external target.

## Safety and non-goals

- No Web session, browser, cookie manager, request replay, or HTTP client.
- No binary exploit, remote tube, debugger, or decompiler integration.
- No MCP, multi-agent system, experience learning, RAG, or vector database.
- No direct Shell path and no change to R1 approval defaults.

All future domain execution remains subject to ToolRuntime, PolicyEngine,
ApprovalManager, workspace isolation, and explicit authorization.
