# RegDelta design

The visual and interaction system for the RegDelta analyst application.
Product truth lives in [PRODUCT.md](PRODUCT.md); this file records how the
interface looks and behaves. It was drafted before the 2026-10 rebuild and is
reconciled against the shipped code at the end of it.

## Direction

**A law lexicon, worked as a tool.** Circulars and the policy manual read like
the pages of a legal lexicon: a fixed measure, a *shoulder* margin down the
outside that indexes paragraphs, evidence, and decisions, *guide words* at the
head naming what is in view, and colour kept inside bordered *plates*.
Navigation, controls, and layout stay the standard ones an analyst already
knows; the lexicon contributes only type, palette, density, and the shoulder.

Chosen through Impeccable's direction round on 2026-10-15 (bolder hand; the
user picked this world over the dealt lead). Rejected: the category default of
a grey console with metric cards and an evidence drawer.

Light only. The scene is office daylight at a desk monitor; a dark theme ships
only if every state, contrast pair, and chart is verified in it.

## Colour

Paper on a desk, slate engraving ink, and colour only where it means something.

| Token | Hex | Use | Contrast |
|---|---|---|---|
| `desk` | `#ECE9E1` | app ground behind leaves | — |
| `paper` | `#FAF8F3` | document leaves, panels | — |
| `paper-raised` | `#FFFFFF` | inputs, the selected index entry | — |
| `ink` | `#1C2230` | text, primary buttons, top bar | 15.0:1 on paper |
| `ink-soft` | `#56606E` | secondary text (slate-tinted, never neutral grey) | 6.0:1 on paper |
| `ink-faint` | `#7A8391` | rules, icons, disabled outlines; never text | 3.6:1 |
| `rule` | `#D9D4C8` | hairlines inside tables and fields only | — |
| `highlight` | `#F1E3B3` | the quoted span; always paired with an underline | ink 12.4:1 on it |
| `focus` | `#2840A8` | focus rings | 8.3:1 |
| `error` | `#A3243B` | failed requests, broken states | 6.9:1 |

Impact plates (text colour on paper and on the plate's own tint):

| Impact | Ink | Tint | On paper / on tint |
|---|---|---|---|
| Conflict | `#B5321C` vermilion | `#F8E4DF` | 5.8 / 5.0 |
| Modified | `#8A5F00` ochre | `#F7EDD3` | 5.3 / 4.8 |
| New requirement | `#2840A8` ultramarine | `#E4E8F7` | 8.3 / 7.2 |
| Already covered | `#0F6E44` emerald | `#DFF0E6` | 5.9 / 5.3 |
| No match | `#6B4F3A` sepia | `#EFE8E1` | 7.1 / 6.2 |

Rules: impact colour appears only inside a bordered plate and always next to
its word; nothing relies on hue alone. One accent does not exist as such:
`ink` carries primary actions and `focus` carries keyboard focus.

## Type

| Role | Face | Size / line | Notes |
|---|---|---|---|
| Document text | Charis SIL 400 | 17px / 1.6 | measure 62ch |
| Headword, page title | Charis SIL 700 | 26px / 1.2 (page), 18px (entry) | |
| Guide words | Charis SIL 700, all small caps | 13px, +0.04em | the only small caps |
| UI body, controls | Public Sans 400–600 | 14px / 1.45 | |
| UI small | Public Sans 500 | 13px / 1.4 | |
| Caption (minimum) | Public Sans 500 | 12px / 1.4 | nothing smaller |

Fixed rem steps, ratio about 1.2; no fluid type. Tabular figures everywhere in
the UI (`font-variant-numeric: tabular-nums`); identifiers such as circular
numbers stay in the UI face, not monospace. Both faces are SIL Open Font
License and self-hosted (`@fontsource`), so no request leaves the machine.

## Space and shape

- 4px base grid: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64. Groups tight,
  separation generous, more space above a heading than below it.
- Leaves and plates have square corners (printed matter); controls take a
  3px radius.
- Hierarchy comes from tone (desk → paper → raised), weight, and size. Rules
  only where rows and fields need them; no outlined boxes for grouping, no
  card grids, no nested cards.
- Depth is flat. Popovers, the only floating layer, take one shadow:
  `0 8px 24px rgb(28 34 48 / 0.16)`.

## The shoulder (signature)

Every reading surface (the circular, the policy clause, the findings index)
is a *leaf*: a guide-word head and a shoulder column.

- **Guide head:** one rule line naming the first and last item in view
  ("¶2 – ¶4", "A.1 – A.6") with the leaf's title between them. It replaces
  label-above-heading eyebrows.
- **Shoulder:** paragraph or clause numbers; a filled arrow at the line where
  the selected quote sits; the analyst's decision mark beside the finding it
  belongs to. Everything in it is functional; it is never ornament.
- Plates: the impact legend, the machine-interpretation plate, and charts on
  the evaluation page are bordered plates; this is where colour lives.

## Evidence states

Three states are always shown separately, each with words and an icon:

1. **Quote status** — *Quotes located* (both quotes found verbatim at the
   stored offsets), *Quote not located* (the quoted text is struck through in
   the plate with the reason; the interpretation is unverified), or *No quote
   to check* (retrieval found no candidate clause; no judgement was made).
2. **Machine interpretation** — the impact plate and rationale, labelled with
   the provider: "Rule-based judge (deterministic demo)" or the model name.
   A model's own score is labelled "model-stated, uncalibrated"; it never
   becomes a percentage or a High/Medium/Low badge.
3. **Analyst decision** — Pending, Accepted, or Rejected with the time,
   shown in the shoulder and on the index entry.

## Components and states

Shared primitives in `frontend/src/components/ui/`: Button (primary, secondary,
quiet), IconButton (always labelled, with a tooltip), Field (visible label,
hint, error), Select, SegmentedControl, Tabs, Table (dense, sticky header,
sortable headers with `aria-sort`), Plate, QuoteStatus, DecisionMark,
GuideHead, Leaf, Notice (info / warning / error / unavailable, each with a
recovery action), Skeleton, EmptyState.

Every interactive element has default, hover, focus-visible, active,
disabled, and busy states. Every data view has loading (skeleton after
300 ms), empty (teaches the next step), zero-result, refused (retrieval
declined), partial (some tasks failed or the run was capped), disconnected
(live trace lost; resyncs), unavailable (provider not configured, with the
variable to set), and error (what failed and how to retry, keeping typed
input).

## Motion

One authored moment: when a finding is selected, the shoulder arrows travel
to the quoted lines, and a decision mark settles into the shoulder when the
decision is saved (180 ms, `cubic-bezier(0.16, 1, 0.3, 1)`, from a visible
default). Everything else is a 120–160 ms colour or opacity change. With
`prefers-reduced-motion: reduce` all of it is instant. No entrance
animations, no looping indicators.

## Layout and responsiveness

Top bar with the product name and six routes (Overview, Circulars, Search,
Assessments, Point in time, Evaluation), collapsing to a menu button under
768px. The assessment workspace:

- ≥ 1440px: findings index (~330px) beside the circular and manual leaves.
- 1024–1439px: index beside one evidence column with the leaves stacked.
- 768–1023px: index collapses into a findings selector above the evidence.
- < 768px: one finding at a time with previous/next; the selected finding and
  scroll context survive width changes.

Selections and filters live in the URL (`?finding=`, `?q=`, `?mode=`,
`?as_of=`) so a refresh or a shared link restores them. Pages reflow at 200%
zoom without horizontal scrolling; long identifiers wrap.

## Accessibility

WCAG 2.2 AA: contrast as tabulated, visible focus on every control, a skip
link, landmark regions, labelled controls, keyboard operation of the findings
index (arrow keys move, Enter selects), focus restored after any overlay, live
regions for trace progress and decision results, text plus icon for every
state, and a table beside every chart.

## Browser surfaces

Text selection uses `highlight` with `ink`; scrollbars, caret, focus rings,
and link underline offset are themed from these tokens.

## Sources

- World: Impeccable catalog world `rw-lexicon-shoulder-and-plate` (law
  lexicon shoulder and plates), adapted to Operate rules.
- Structure reference: VoltAgent/awesome-design-md @ `3b60532`,
  `design-md/ibm/DESIGN.md` (MIT) — the 4px grid, sentence-case labels over
  tracked eyebrows, hierarchy by tone and weight rather than shadow, one-accent
  discipline, and dense rule-separated tables. IBM's identity (Plex, IBM Blue,
  square controls) is not used.
- Review method: Leonxlnx/taste-skill (`design-taste-frontend`) redesign mode:
  lint and inspector findings are in `docs/maintenance/frontend-baseline.md`.
