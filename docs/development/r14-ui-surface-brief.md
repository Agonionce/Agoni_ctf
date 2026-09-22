# R14.1 Challenge Workbench Surface Brief

## Scope and Mode

Operate mode. The first surface lets one local user scan imported challenges,
create a new challenge, and review its imported material. Runtime control and
technical process inspection are outside this phase.

## User Job

The user should be able to answer three questions without technical context:

1. Which challenges exist?
2. Which one should I open?
3. How do I add another?

## Chosen Direction

Archival accession register. The challenge catalog aligns to one blue
registration rail; every record is a ledger row rather than a dashboard card.
The approved north-star comp is
`.impeccable/mocks/r14-challenge-catalog-ledger.png`.

The memorable moment is the catalog resolving around one continuous
registration rail. Its short entry motion draws only that rail and is removed
when reduced motion is requested.

## First Viewport

- A quiet top bar holds the Agonionce wordmark, two navigation destinations,
  and one primary new-challenge action.
- A large `题目` heading and one sentence explain the catalog.
- Full-width challenge rows begin in the first viewport and align to a numbered
  registration rail.
- Empty state and failure state occupy the same ledger geometry.

## Fidelity Inventory

| Comp ingredient | Implementation medium | Commitment |
| --- | --- | --- |
| Top navigation | Semantic HTML and CSS | Minimal, no application sidebar |
| Registration rail | CSS geometry | One continuous off-centre blue line |
| Challenge records | Semantic links and CSS grid | Full-width rows, never a card wall |
| Status marks | Text plus CSS border/shape | Color never carries state alone |
| New challenge action | Semantic link/button | Only saturated action in the header |
| Empty state | Semantic HTML | Reuses the ledger endpoint |
| Paper and rules | CSS | Flat, low-contrast, no raster texture |
| Comp imagery | Accepted omission | The comp is a north star, not a shipped asset |

## Responsive Rules

The catalog remains a single reading flow. At narrow widths, dates fold beneath
the title, the navigation labels compact, and the registration rail stays
visible. Rows never become floating cards.

## Constraints

- Chinese-first copy with a locally bundled Simplified Chinese serif display face.
- Raw HTML in Markdown is never executed.
- No challenge identifiers, workspace paths, tool output, policy records, or
  internal evidence structure in the primary UI.
- No invented challenge metrics or example records in production.
