---
name: Agonionce Local Challenge Workbench
description: A quiet local CTF workbench organized like an archival accession register.
colors:
  cobalt: "#2458c6"
  cobalt-deep: "#173f99"
  cobalt-pale: "#d7e2f7"
  cobalt-wash: "#eef3fc"
  ink: "#172033"
  muted-ink: "#5f6b7f"
  faint-ink: "#667085"
  cool-paper: "#f7f9fc"
  white-paper: "#ffffff"
  rule: "#d6deeb"
  rule-strong: "#9cb2dc"
  vermilion: "#bd3d2d"
  vermilion-wash: "#fff4f1"
  success: "#286747"
  warning: "#9a5918"
typography:
  display:
    fontFamily: '"Noto Serif SC", Georgia, serif'
    fontSize: "clamp(2.7rem, 6vw, 4.9rem)"
    fontWeight: 600
    lineHeight: 1.05
    letterSpacing: "-0.035em"
  title:
    fontFamily: '"Noto Serif SC", Georgia, serif'
    fontSize: "1.19rem"
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: "-0.012em"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.75
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif'
    fontSize: "0.76rem"
    fontWeight: 650
    lineHeight: 1
    letterSpacing: "0.08em"
rounded:
  stamp: "4px"
  quiet: "7px"
  control: "9px"
  sheet: "12px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "38px"
  section: "54px"
components:
  button-primary:
    backgroundColor: "{colors.cobalt}"
    textColor: "{colors.white-paper}"
    rounded: "{rounded.control}"
    padding: "0 18px"
    height: "42px"
  button-secondary:
    backgroundColor: "{colors.white-paper}"
    textColor: "{colors.muted-ink}"
    rounded: "{rounded.control}"
    padding: "0 18px"
    height: "44px"
  input:
    backgroundColor: "{colors.white-paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "48px"
  status-attention:
    backgroundColor: "{colors.vermilion-wash}"
    textColor: "{colors.vermilion}"
    rounded: "{rounded.stamp}"
    padding: "7px 9px"
  approval-folio:
    backgroundColor: "{colors.vermilion-wash}"
    textColor: "{colors.ink}"
    padding: "30px 0"
---

# Design System: Agonionce Local Challenge Workbench

## Overview

**Creative North Star: "The Accession Register / 档案登记册"**

Agonionce feels like a carefully maintained local archive: calm, exact, and
easy to scan. Cool paper, charcoal text, cobalt registration rules, and
full-width records make the challenge itself the subject. Internal planning,
tool output, and implementation stages stay out of the user-facing surface.

The system is restrained rather than sterile. A locally bundled Chinese serif
face gives titles archival authority, while a system sans-serif keeps forms and
supporting copy fast to read. Vermilion appears only when the user must act.

**Key Characteristics:**

- Continuous registration rails organize challenge records and stage outcomes.
- Full-width rows replace dashboard cards and metric tiles.
- Serif titles and sans-serif controls create a clear reading hierarchy.
- Status is always written in words; color only reinforces meaning.
- Motion is brief and structural: the catalog rail draws once and a newly
  required approval enters as one folio reveal. Both are removed when reduced
  motion is requested.

## Colors

The palette is cool and paper-like, with cobalt as the single active voice and
vermilion reserved for action-required states.

### Primary

- **Registrar Cobalt** (`#2458c6`): primary actions, the registration rail,
  active navigation, and meaningful focus relationships.
- **Archive Cobalt** (`#173f99`): hover states and high-contrast cobalt text.
- **Cobalt Wash** (`#eef3fc`): quiet hover and file-picker backgrounds.

### Neutral

- **Charcoal Ink** (`#172033`): default body text.
- **Muted Annotation** (`#5f6b7f`): secondary copy and mobile metadata.
- **Cool Paper** (`#f7f9fc`): page background.
- **White Sheet** (`#ffffff`): inputs and focused working surfaces.
- **Ledger Rule** (`#d6deeb`): ordinary dividers and field grouping.
- **Strong Ledger Rule** (`#9cb2dc`): table headers and structural boundaries.

### Tertiary

- **Vermilion Stamp** (`#bd3d2d`): errors and states that require attention.
- **Confirmed Green** (`#286747`): completed outcomes.
- **Unresolved Ochre** (`#9a5918`): unsolved outcomes.

**The One Active Voice Rule.** Cobalt identifies interaction; vermilion is rare
and appears only when the user must respond.

## Typography

**Display Font:** Noto Serif SC (with Georgia and serif fallback)

**Body Font:** System sans-serif with PingFang SC fallback

**Label/Mono Font:** System sans-serif for labels; system monospace only for
registration indices and code.

**Character:** Serif headings make each challenge feel recorded rather than
advertised. Sans-serif labels, fields, and explanations stay compact and
operational.

### Hierarchy

- **Display** (600, `clamp(2.7rem, 6vw, 4.9rem)`, 1.05): one page title per
  surface, balanced and limited to roughly 16 characters per line.
- **Title** (500, `1.19rem`, 1.35): challenge names and empty-state headings.
- **Body** (400, `1rem`, 1.75): descriptions with a maximum reading width near
  54–72 characters.
- **Label** (650, `0.76rem`, `0.08em`): register headers and concise metadata.

**The Recorded, Not Broadcast Rule.** Display type creates authority without
turning the interface into a marketing hero.

## Layout

The main container is capped at `1240px` with 24px side gutters on desktop and
14px on narrow screens. Catalog records align to an off-center rail and use a
five-column grid for index, name, domain, status, and date. The challenge
workbench uses a quiet horizontal tab register and one reading column; progress
and outcome sections align their labels on a 180px subgrid. Forms stay in a
single 920px column; only closely related short fields and file groups share a
row.

At `980px`, navigation moves to a second header row, catalog columns tighten,
and outcome grids reduce without dropping meaning. At `700px`, the catalog
becomes a three-column reading flow: date and domain fold below the title while
status remains at the right. Form grids, detail registers, approval folios,
milestones, and outcome sections become one reading column. The two approval
actions remain adjacent; endpoint rows fold to two columns with parameters on
their own line and access status retained. Tabs stay horizontally scrollable.
The rail remains visible down to 320px; rows never turn into floating cards.

## Elevation & Depth

The system is flat by default. Paper tone and one-pixel rules establish depth;
shadows are reserved for the primary action, its hover response, and the report
sheet whose elevation communicates a document laid above the register. Inputs
use a cobalt focus ring instead of elevation.

- **Primary action:** `0 7px 18px rgba(36, 88, 198, 0.2)` at rest and a slightly
  stronger shadow on hover.
- **Soft ambient:** `0 16px 40px rgba(32, 54, 96, 0.09)` is available only for a
  genuinely lifted sheet or temporary surface, not ordinary sections.

**The Flat-by-Default Rule.** Structure comes from registration lines and
spacing, never from a wall of elevated containers.

## Shapes

Controls use restrained 7–9px corners. Attention states use a tighter 4px stamp
radius, and the report sheet alone uses a soft 12px paper corner. Records,
sections, approvals, and tables remain square-edged and are formed by rules
rather than enclosing cards. The circular registration marker is the single
recurring round silhouette.

## Components

### Buttons

- **Primary:** cobalt fill, white label, 9px radius, 42px minimum height, and
  one-pixel cobalt border.
- **Hover / focus:** deepen to Archive Cobalt with a one-pixel lift; keyboard
  focus uses the shared visible cobalt outline.
- **Secondary:** white paper, ledger border, muted text, and no resting shadow.

### Inputs / Fields

- **Style:** white sheet, 1px blue-gray stroke, 9px radius, and 48px minimum
  height. Textareas share the stroke and use generous 1.75 line-height.
- **Focus:** cobalt border with a four-pixel translucent cobalt ring.
- **Error / disabled:** errors use Vermilion Stamp plus written guidance;
  disabled primary actions become neutral and lose elevation.

### Navigation

Navigation is a quiet centered word list. The active destination gains a 2px
cobalt underline; the far-right new-challenge action is the only filled control
in the header. At medium widths navigation folds onto its own ruled row.

### Accession Row

Each record is one full-width link attached to the registration rail. Index,
title, domain, written status, and creation date remain aligned for scanning.
Hover adds a flat cobalt wash and a small directional cue; it never adds a card
border or shadow.

### Status Stamp

Ordinary states are text only. Waiting and help-required states gain a thin
vermilion border and wash; completed, paused, and unresolved states keep their
written label and use color only as reinforcement.

### Workspace Tabs

Tabs are a horizontal text register below the challenge heading. The selected
view gains a 2px cobalt underline and written selection semantics. Arrow keys,
Home, and End move focus and selection; narrow screens scroll the same register
instead of replacing it with a menu.

### Approval Folio

An approval appears inline at the top of the active workbench, bounded by thin
vermilion rules and a flat wash with a brief directional reveal. It contains one
plain-language action, one risk phrase, and explicit reject/allow controls.
Focus moves to it when it arrives. It never shows tool names, raw arguments,
payloads, or candidate values.

### Milestone and Outcome Ledgers

Milestones use a single vertical cobalt rail and short completed-stage copy.
Outcome groups use the familiar 180px section label subgrid and full-width
records. Facts, findings, hypotheses, experiments, and evidence are separate
sections with written status and certainty labels; none become dashboard tiles.

### Report Sheet

Reports use one centered white sheet with a 12px corner and low ambient shadow.
The content remains Markdown reading copy with a 72-character measure. A small
three-way switch chooses analysis report, solution record, or lessons without
opening a new surface.

### Experience Candidate

Candidates are ruled ledger rows with category, kind, written review status,
strategy, and lesson. Pending rows expose explicit “忽略” and “纳入经验”
actions; reviewed rows become read-only.

## Do's and Don'ts

### Do:

- **Do** lead every page with one clear user task and one sentence of context.
- **Do** keep challenge rows attached to the continuous registration rail.
- **Do** show user outcomes such as “材料已导入” and “题目已准备好.”
- **Do** show only stage-level milestones, then route deeper conclusions into
  the Outcomes or Reports view.
- **Do** reserve the inline vermilion folio for an actual pending user decision.
- **Do** preserve dates, written status, focus visibility, and reduced motion on
  every responsive breakpoint, with increased-contrast and forced-color support.

### Don't:

- **Don't** replace the register with a card wall, metric dashboard, or sidebar.
- **Don't** expose planner traces, tool logs, workspace paths, IDs, or roadmap
  phases as primary UI content.
- **Don't** show raw action arguments, payloads, credentials, cookies, headers,
  or candidate answer values in approvals, outcomes, or reports.
- **Don't** use terminal black, neon cyberpunk accents, gradients, or decorative
  glass surfaces.
- **Don't** use vermilion as decoration or let color become the only status cue.
