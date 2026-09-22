# Agonionce R14 Local UI Foundation

## Status

R14.1 through R14.4 are implemented and locally validated as one governed
challenge workbench.

## Purpose

R14 gives a local user a concise interface for creating and reviewing
authorized CTF challenges. It translates existing persisted state into
user-facing stage outcomes without exposing internal orchestration noise.

## Ownership

R14 introduces a Presentation Layer under `webui/`. It owns HTTP presentation
contracts, static UI delivery, upload staging, and user-facing projections. It
does not own challenge validation, workspace copying, Runtime decisions,
approval policy, Tool execution, Intelligence conclusions, or Completion.

```text
Browser on loopback
  -> Web UI presentation service
  -> ChallengeImporter / complete local read projections
  -> Runtime-owned SupervisedRunCoordinator (run controls and session authorization)
  -> AgentRuntime -> ToolRuntime -> PolicyEngine -> ApprovalManager
  -> Completion / Experience candidate coordinators
```

The Presentation Layer calls existing coordinators directly. It must not parse
CLI output, read `config.json` into the browser, call a Tool backend, or create
an alternate execution path.

## R14.1 Scope

- Loopback-only local service.
- Challenge catalog with concise status projection.
- Challenge creation with Markdown description.
- Attachment and source-file upload through temporary contained staging.
- Existing Challenge Intake validation and workspace bootstrap.
- Challenge detail with imported material metadata.
- Desktop-first responsive UI, keyboard access, and safe Markdown preview.

## R14.2 Scope

- Start an automatically authorized, challenge-local run through the existing
  Runtime integration factory.
- Present concise milestones and the single Flag outcome instead of repeated
  action-confirmation prompts.
- Safely abort at an AgentRuntime boundary and resume from a typed checkpoint.
- Keep raw action arguments, reasoning, stdout, and live logs server-side while
  exposing recorded Flag values, evidence, and paths in the local result view.

## R14.3 Scope

- Read-only projections for facts, findings, hypotheses, experiments, evidence,
  artifact metadata, and passive Web observations.
- Complete local report, writeup, and lessons views with the final Flag,
  supporting evidence, and recorded paths.
- Clear separation between confirmed observations and unresolved hypotheses.

## R14.4 Scope

- Explicit approve or reject controls for sanitized Experience candidates.
- Approval uses the existing candidate catalog and is the only UI path that may
  add a candidate to global Experience; rejection has no global side effect.
- Keyboard-operable workspace navigation, focus transfer for pending decisions,
  live status announcements, reduced-motion, increased-contrast, and forced-color
  support.

The final workbench keeps four stable views: **概览** contains run controls,
milestones, description, and materials; **成果** leads with the one Flag and
then separates facts, findings, hypotheses, experiments, evidence, artifact
metadata, and Web observations; **报告** reads complete local completion
documents; **经验** reviews sanitized reusable candidates. Outcomes, documents, and candidates load
independently, so one unavailable projection does not mislabel or blank the
other views.

## Explicit Non-goals

- Live Planner, Analyzer, Policy, Tool, stdout, or audit-stream display.
- Public hosting, remote access, accounts, teams, or multi-user review.
- Archive extraction, source execution, browser automation, crawling, scanning,
  payload generation, or public-target autonomy.
- Editing persisted Intelligence, reports, or challenge answers.
- Direct Tool execution, automatic Experience approval, or automatic flag
  submission from the Presentation Layer.

## Security Boundary

- The server binds to `127.0.0.1` unless a future governed phase changes the
  contract.
- Upload file names are normalized and sensitive names are rejected before
  staging.
- Uploads have bounded per-file and per-request sizes and are removed after the
  existing importer copies accepted inputs.
- Challenge text, URL, source-root, and workspace validation remain owned by
  the existing Challenge Intake Layer.
- The browser receives complete challenge-local intake and outcome projections,
  including recorded values, evidence, and absolute or relative paths. It never
  receives `config.json`, Tool authority, private checkpoints, or live raw
  action execution. This is an operator-facing local workbench; the same data
  remains challenge-local and is not copied into global Experience.
- Runtime configuration remains server-side. The supervised coordinator uses a
  session-level pre-authorization resolver for policy-allowed actions, while
  PolicyEngine, ToolRuntime, ApprovalManager, audit, containment, high-risk
  denial, and abort behavior remain in force.
- Resume loads only the latest typed, challenge-bound checkpoint. Invalid or
  cross-challenge checkpoints fail closed.
- Markdown preview treats raw HTML as text and never executes JavaScript.

## Validation

- Deterministic API tests use temporary workspaces and experience roots.
- Negative tests cover sensitive filenames, oversized inputs, duplicate names,
  invalid URLs, empty descriptions, and path-like upload names.
- Frontend component tests cover persistent ARIA tab targets, arrow/Home/End
  keyboard routing, visible-panel switching, partial loading failures,
  automatic-run announcements, retry, and focus recovery. Empty, loading, success, and
  failure copy is explicit in-flow.
- A local demo creates a fake-local challenge and opens no network target.
- Supervised-run tests use an injected fake Runtime, exercise automatic
  authorization, abort, typed resume, complete local projections, and candidate
  review, and invoke no Tool.

Run the contract demo with:

```bash
python -m demos.r14_local_ui_workbench
python -m demos.r14_supervised_workbench
```

Build and launch the browser interface with:

```bash
cd webui/frontend && npm install && npm test && npm run build
cd ../..
python main.py ui start
```

Both demos are deterministic and contact no target. R14.1 through R14.4 pass
the local test suite and frontend production build.
