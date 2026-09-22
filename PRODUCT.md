# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated: React, TypeScript, and Vite for the user interface, backed by a
loopback-only FastAPI presentation service. This keeps the interaction layer
typed and delivers supervised run milestones without coupling the browser to
CLI output or runtime storage.

## Users

The primary user is an authorized CTF participant or security learner working
locally on one challenge at a time. They want to create a challenge quickly,
attach the provided material, and understand the agent's meaningful progress
without reading internal orchestration details.

## Product Purpose

Agonionce turns an authorized challenge description and local inputs into a
controlled, evidence-backed solving workflow. The local UI makes challenge
intake and later run milestones approachable while preserving the existing
policy, approval, workspace, evidence, and audit boundaries.

## Positioning

Agonionce presents reliable stage outcomes from a governed CTF research loop;
it does not expose an unrestricted terminal, a generic chatbot transcript, or
an opaque autonomous attack process.

## Operating Context

The product runs on the user's computer and works with Markdown challenge
descriptions, optional authorized target metadata, attachments, source files,
isolated workspaces, persisted runs, reports, writeups, and reviewed reusable
experience. The local workbench covers challenge intake, supervised analysis,
concise outcomes, completion documents, and explicit experience review.

## Capabilities and Constraints

- Challenge names, descriptions, domains, optional HTTP(S) target URLs,
  attachments, and source files use the existing Challenge Intake contracts.
- Uploaded content is copied into a contained workspace; it is not executed or
  automatically extracted.
- Sensitive file names, credential-shaped text, unsafe paths, and embedded URL
  credentials fail closed.
- The service binds to loopback by default and provides no public-network,
  multi-user, browser-automation, scanning, or Tool execution authority.
- A Runtime-owned coordinator may start, safely stop, and resume a run; every
  actual operation still passes through the existing policy and approval path.
- Users see only meaningful milestones and a sanitized action description when
  a decision is required. Raw Planner, Tool, Policy, checkpoint, log, path,
  payload, credential, and answer values never enter the browser contract.
- Facts, findings, hypotheses, experiments, and evidence stay visibly distinct;
  a recorded observation is never presented as an automatic conclusion.
- Reusable experience remains pending until the user explicitly approves or
  rejects it. Approval alone may add sanitized global memory.
- Attachment size limits remain an implementation safety setting rather than a
  product claim.

## Brand Commitments

The product name is Agonionce. User-facing copy is concise, calm, Chinese-first,
and precise about authorization and uncertainty. The interface must not use a
neon hacker-terminal aesthetic or imply exploit capability that the product
does not have.

## Evidence on Hand

The repository contains implemented Challenge Intake, workspace containment,
artifact metadata, Runtime, approval, Intelligence, Web Research, Completion,
Experience, deterministic tests, fake-local demonstrations, and a loopback-only
React workbench. The established visual system is the archival accession
register documented in `DESIGN.md`; there is no separate logo system or public
customer proof.

## Product Principles

- Show the outcome of a stage, not the machinery that produced it.
- Ask the user only when their input or approval is necessary.
- Keep local authorization and containment visible without adding friction.
- Preserve evidence and uncertainty even when the interface summarizes them.
- Make the next action obvious and keep secondary detail on demand.

## Accessibility & Inclusion

The interface is keyboard accessible, does not encode state by color alone,
supports reduced motion, increased contrast, and forced colors, uses readable
Chinese text sizing, and keeps focus, live status, approval, and error feedback
explicit. Pending decisions receive focus without opening a modal.
