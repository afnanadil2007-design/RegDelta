---
name: RegDelta
description: A regulatory-change review desk where circulars and the compliance manual are read like a law lexicon.
colors:
  desk: "#E2DED4"
  paper: "#FAF8F3"
  paper-raised: "#FFFFFF"
  ink: "#1C2230"
  ink-soft: "#56606E"
  ink-faint: "#7A8391"
  rule: "#D9D4C8"
  highlight: "#F1E3B3"
  focus: "#2840A8"
  error: "#A3243B"
  error-tint: "#F7E1E5"
  conflict: "#B5321C"
  conflict-tint: "#F8E4DF"
  modified: "#8A5F00"
  modified-tint: "#F7EDD3"
  new: "#2840A8"
  new-tint: "#E4E8F7"
  covered: "#0F6E44"
  covered-tint: "#DFF0E6"
  none: "#6B4F3A"
  none-tint: "#EFE8E1"
  ink-hover: "#2C3445"
  ink-pressed: "#0F141D"
  bar-bright: "#FFFDF6"
  bar-text: "#E9E5DA"
  bar-muted: "#C9C3B4"
typography:
  page-title:
    fontFamily: "Charis SIL, Georgia, serif"
    fontSize: "1.625rem"
    fontWeight: 700
    lineHeight: 1.2
  verdict:
    fontFamily: "Charis SIL, Georgia, serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.25
  headword:
    fontFamily: "Charis SIL, Georgia, serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.3
  leaf-title:
    fontFamily: "Charis SIL, Georgia, serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.45
  document:
    fontFamily: "Charis SIL, Georgia, serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.6
  guide-words:
    fontFamily: "Charis SIL, Georgia, serif"
    fontSize: "0.8125rem"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "0.04em"
    fontFeature: "small-caps (font-variant-caps)"
  ui-large:
    fontFamily: "Public Sans Variable, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tnum"
  body:
    fontFamily: "Public Sans Variable, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tnum"
  label:
    fontFamily: "Public Sans Variable, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.4
    fontFeature: "tnum"
  caption:
    fontFamily: "Public Sans Variable, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
    fontFeature: "tnum"
rounded:
  none: "0px"
  inner: "2px"
  control: "3px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  shoulder: "2.25rem"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "6px 16px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.ink-hover}"
    textColor: "{colors.paper}"
  button-primary-active:
    backgroundColor: "{colors.ink-pressed}"
    textColor: "{colors.paper}"
  button-secondary:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 16px"
    height: "36px"
  button-secondary-hover:
    backgroundColor: "{colors.paper}"
  button-secondary-active:
    backgroundColor: "{colors.desk}"
  button-quiet:
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 16px"
    height: "36px"
  button-quiet-hover:
    backgroundColor: "{colors.paper-raised}"
  input:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
    height: "36px"
  input-disabled:
    backgroundColor: "{colors.desk}"
    textColor: "{colors.ink-soft}"
  segmented-option-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.inner}"
    padding: "6px 12px"
  leaf:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "16px 20px"
  plate-neutral:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
  plate-modified:
    backgroundColor: "{colors.modified-tint}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
  impact-tag-conflict:
    backgroundColor: "{colors.conflict-tint}"
    textColor: "{colors.conflict}"
    rounded: "{rounded.none}"
    padding: "1px 6px"
  notice-error:
    backgroundColor: "{colors.error-tint}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
  top-bar:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.bar-text}"
    height: "56px"
  index-entry-selected:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
---

# Design System: RegDelta

Recorded from the shipped frontend (2026-10-15). Tokens in the frontmatter mirror
`frontend/src/index.css` (`:root`) and `frontend/tailwind.config.js`; where this
file and the code disagree, the code is right and this file is stale. Product
truth lives in [PRODUCT.md](PRODUCT.md).

## Overview

**Creative North Star: "A law lexicon, worked as a tool"**

Circulars and the policy manual are set as pages of a legal lexicon. Each
reading surface is a *leaf* of uncoated paper on a warm grey desk. A guide-word
head names what is in view, a *shoulder* column down the outside carries
paragraph and clause numbers, and a solid arrow and the analyst's decision tick
hang on the line where the evidence starts. Colour sits inside double-ruled
*plates* and small ruled tags, and it always appears next to its word.

Navigation, forms, tables and buttons are the standard web controls an analyst
already knows. The lexicon supplies type, palette, density and the shoulder,
and nothing else. The interface is dense and quiet. Hierarchy comes from tone
(desk, then paper, then raised white), from weight and from the serif/sans
split, not from shadow. Light theme only (`color-scheme: light`). There is no
dark theme in the build.

The rejected default was a grey console with metric cards and an evidence
drawer.

**Key Characteristics:**
- Paper leaves on a desk ground, with square corners and no shadows.
- Charis SIL for documents, headwords and guide words. Public Sans for controls and data, with tabular figures.
- A shoulder (2.25rem) of paragraph and clause numbers. The arrow and tick sit at the first line of the evidence mark.
- Colour appears only in plates, impact tags and notices, and always with a word.
- Quote status, machine interpretation and analyst decision are shown as three separate states, each with words and an icon.
- Two authored motions, both 180ms `cubic-bezier(0.16, 1, 0.3, 1)`: the shoulder arrow and tick travelling to the next quoted line, and the decision tick settling in.

## Colors

Paper, slate engraving ink, and five impact inks, each paired with its own
tint.

### Primary
- **Slate Engraving Ink** (#1C2230): all text, primary buttons, the selected segment, the top bar, rules under guide heads and table headers (1.5px). 14.98:1 on paper, 11.84:1 on desk, 15.90:1 on raised.
- **Ink, hover** (#2C3445) and **Ink, pressed** (#0F141D): primary-button states. #2C3445 is also the divider of the phone menu.

### Neutral
- **Desk** (#E2DED4): the app ground (`html`) behind every leaf. It is also the pressed state of secondary and quiet buttons, the disabled field fill, and the chart hover cursor.
- **Uncoated Paper** (#FAF8F3): leaves, panels, memo and trace sections.
- **Raised White** (#FFFFFF): inputs, secondary buttons, the selected findings-index entry, and the ground of the neutral plate.
- **Slate Soft** (#56606E): secondary text, shoulder numbers on unselected clauses, and placeholders. 6.01:1 on paper, 4.75:1 on desk, 6.38:1 on raised, 4.97:1 on highlight, and 5.12 to 5.47:1 on every tint.
- **Slate Faint** (#7A8391): control borders, the neutral plate's rule, and the scrollbar thumb. Never use it for text: 3.61:1 on paper, 3.83:1 on raised, 2.85:1 on desk.
- **Rule** (#D9D4C8): hairlines between table rows and skeleton bars. 1.39:1 on paper; it marks rows and is not meant to be read.
- **Highlight** (#F1E3B3): the quoted span, text selection and `<mark>`. Ink on it is 12.4:1. On a quote it always comes with a 2px ink underline (`inset 0 -2px 0`).
- **Focus Ultramarine** (#2840A8): the 2px focus outline with 2px offset. 8.28:1 on paper, 6.54:1 on desk.
- **Error Crimson** (#A3243B) on **Error Tint** (#F7E1E5): failed requests, a quote that was not located (struck through), and field errors. 6.89:1 on paper, 5.87:1 on its tint.

### Impact inks (plates and tags only)

| Impact | Ink | Tint | on paper | on own tint | ink text on tint |
|---|---|---|---|---|---|
| Conflict | vermilion #B5321C | #F8E4DF | 5.76 | 4.99 | 12.99 |
| Modified | ochre #8A5F00 | #F7EDD3 | 5.32 | 4.84 | 13.63 |
| New requirement | ultramarine #2840A8 | #E4E8F7 | 8.28 | 7.19 | 13.01 |
| Already covered | emerald #0F6E44 | #DFF0E6 | 5.93 | 5.32 | 13.43 |
| No match | sepia #6B4F3A | #EFE8E1 | 7.05 | 6.17 | 13.10 |

Notices reuse two of these pairs: info uses new and new-tint, warning uses
modified and modified-tint. The evaluation chart's bars use `new`.

### Top bar
- **Bar Bright** (#FFFDF6): the wordmark, the active route with its 3px inset underline, and trouble status. 15.62:1 on ink.
- **Bar Text** (#E9E5DA): the bar's base text colour. 12.63:1 on ink.
- **Bar Muted** (#C9C3B4): inactive routes and normal status text. 9.05:1 on ink.

These three, and the two ink states, are literals in `AppShell.tsx` and
`controls.tsx`. They are not CSS variables.

### Named Rules
**The Plate Quarantine Rule.** Impact colour appears only inside a ruled element: a plate, an impact tag, or a notice. It always sits next to the word it codes. Nothing relies on hue alone.

**The No Accent Rule.** No brand accent exists. Ink carries primary actions and ultramarine carries keyboard focus.

## Typography

**Document Font:** Charis SIL 400/700 and 400 italic (fallback Georgia, serif)
**UI Font:** Public Sans Variable (fallback system-ui, sans-serif)

Both faces are self-hosted through `@fontsource`, so no font request leaves the
machine.

**Character:** a bookish slab-serif for anything that is source text or names a
document, and a plain civic sans for everything you operate. The body sets
`tabular-nums`. Document text turns it off (`font-variant-numeric: normal`).

### Hierarchy
- **Page title** (Charis 700, 26px / 1.2): `PageHeader` h1, with its context line underneath in UI 14px slate soft. No label is ever placed above it.
- **Verdict** (Charis 700, 22px / 1.25): the impact word heading the verdict plate, in the impact ink.
- **Headword** (Charis 700, 18px / 1.3): the circular number or manual name in a leaf, and empty-state titles.
- **Leaf title** (Charis 700, 16px / 1.45): the centred title inside a guide head, findings-index entries, and section heads (Memo, Agent trace).
- **Document** (Charis 400, 17px / 1.6, `.doc-text`): circular paragraphs, clauses, search passages and the memo. `max-width: 62ch`, `hyphens: manual`, `overflow-wrap: break-word`.
- **Guide words** (Charis 700, 13px, small caps, +0.04em): first and last items in a guide head, shoulder numbers, and the "Impact" title of the legend plate. These are the only small caps in the system.
- **Section caps** (Charis 700, 13px, +0.06em): a circular's own upper-case section heading, set as printed.
- **UI large** (Public Sans 400, 16px / 1.45): the verdict rationale and phone menu links.
- **Body** (Public Sans 400 to 600, 14px / 1.45): controls, tables and notices.
- **Label** (Public Sans 600, 13px / 1.4): field labels, legends and table headers.
- **Caption** (Public Sans 500, 12px / 1.4): hints, tags and top-bar status. Nothing is set smaller.

The scale uses fixed rem steps (12, 13, 14, 16, 17, 18, 22, 26), ratio about
1.2, with no fluid type. A 32px step (`text-3xl`) is defined in the config but
nothing uses it.

### Named Rules
**The Two Faces Rule.** Charis is for what is read, Public Sans is for what is operated. Identifiers such as circular numbers stay in a text face, never monospace. They may break only after a slash (`Ident`).

**The Measure Is a Ceiling Rule.** `62ch` caps document text but does not set it. In Charis, 62ch comes out at roughly 70 to 72 average characters per line, which is what the full-width memo shows. In the assessment workspace the columns set the line length. At 1440 the leaves run about 49 to 57 characters per line (the text column is about 434px). At 1024 they run about 43 to 50. The two documents sit side by side because that comparison matters more than a longer line.

## Layout

The page is a sticky ink top bar, 56px high. The content area is capped at
`max-width: 1680px`, with 16px side padding (24px from 640px). Main has 24px of
vertical padding, or 32px from 1024px. A 4px grid governs spacing (4, 8, 12,
16, 20, 24, 32). Gaps between leaves are 16px, and 20px on the overview,
circular and point-in-time pages. Groups are tight and separations generous.

The shoulder is the structural grid of every reading surface:
`grid-template-columns: 2.25rem minmax(0,1fr)`. Leaves put a 20px gap after
the shoulder, and the findings index puts 8px.

**Assessment workspace**, with the selection and impact filter in the URL
(`?finding=`, `?impact=`):
- **1440px and wider (`wide`):** a 300px findings index (sticky at 4.5rem, scrolling inside its own column) beside two equal leaves, circular and manual. Three columns on one grid.
- **1024–1439px (`lg`):** the impact legend and a compact finding picker (a select labelled "Finding n of N" with previous and next icon buttons) above the circular and manual leaves, side by side.
- **Below 1024px:** the same picker above the leaves, stacked circular then manual.

The verdict plate sits at the foot of the circular leaf. The decision bar sits
at the foot of the manual leaf. Memo and agent trace follow at full width.

Other routes use a main column plus a side column from 1024px: 380px, or 440px
at `wide`, on the overview; 360px, or 420px, on the circular. Point in time
uses two equal columns from 1024px. The top bar's routes collapse into a menu
button below 768px. The system status line shows only from 1024px, or inside
the phone menu.

Wide tables scroll inside their own labelled, focusable region, so the page
never scrolls sideways.

## Elevation & Depth

The system is flat. Depth comes from tone: desk, then paper, then raised
white. Leaves and plates cast no shadow.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 8px 24px rgb(28 34 48 / 0.16)`): only on the icon-button tooltip, the one floating layer.
- **Plate inner rule** (`box-shadow: inset 0 0 0 3px <tint>, inset 0 0 0 4px <ink>`): draws a printed rule, not depth (see Shapes).
- **Quote underline** (`box-shadow: inset 0 -2px 0 var(--ink)`): draws a rule, not depth.
- **Active route** (`box-shadow: inset 0 -3px 0 #FFFDF6`): draws a rule, not depth.

### Named Rules
**The Tone Not Shadow Rule.** Separate surfaces by stepping desk, paper and raised white. Use box-shadow only to draw rules, with the tooltip as the one exception.

## Shapes

Leaves, plates, tags and notices have square corners, like printed matter.
Controls take a 3px radius (`rounded-control`). Segmented options inside a
control take 2px. The decision tick's paper backing is circular, so it covers
the shoulder behind it.

Rules carry the structure:
- **1.5px ink** under every guide head, table header, decision bar and section head.
- **1px rule** between table rows.
- **Plates are double-ruled.** A 1.5px outer border in the plate's ink, a 3px band of the plate's ground, then a 1px inner hairline in the same ink (`Plate` in `lexicon.tsx`). The neutral plate (impact legend, evaluation chart) uses slate faint on raised white.
- **Notices, impact tags and the synthetic tag are single-ruled** (1px).

### Named Rules
**The Double Rule Rule.** Only plates carry the double rule, because a plate is where interpretation and colour live. Notices and tags stay single-ruled, so they never read as a plate.

## Components

### Buttons
- **Shape:** gently squared (3px), at least 36px high, padded 6px 16px, 14px semibold, with an optional 16px leading icon and an 8px gap.
- **Primary:** ink fill, paper text. Hover #2C3445, pressed #0F141D.
- **Secondary (default):** raised white with a 1px ink border. Hover goes to paper, pressed to desk.
- **Quiet:** transparent and borderless. Hover raised, pressed desk.
- **States:** a 150ms colour transition. Disabled is 50% opacity with a not-allowed cursor. Busy shows a spinner in place of the icon and blocks repeat clicks (`aria-busy`). Accept and Reject become primary when they match the saved decision (`aria-pressed`).
- **Icon button:** 36px square and always labelled. The tooltip is ink with paper text, 12px, with the float shadow, and it appears on hover and on keyboard focus.

### Inputs / Fields
- **Style:** raised white, 1px slate-faint border, 3px radius, 36px minimum height, 14px text, slate-soft placeholder.
- **Hover:** the border darkens to ink. **Focus:** the global 2px ultramarine outline with 2px offset.
- **Error:** crimson border plus a 12px crimson message tied by `aria-describedby`. **Disabled:** desk fill with slate-soft text.
- **Field:** a visible 13px semibold label above the control, then a hint or an error, never both.
- **Segmented control:** joined options in a raised, faint-bordered track. The selected option is ink-filled.

### Leaf (signature)
A paper section, padded 16px and 20px from 640px. It has a **guide head**: one
1.5px ink rule line with the first item in view on the left, the leaf's title
centred, and the last item on the right, all in guide words. Below the head
sits the headword, a 13px slate-soft meta line, and a synthetic tag where the
material is generated. The text runs in the shoulder grid. Neighbouring,
uncited clauses are set in slate soft.

### Shoulder pointer and decision tick (signature)
`MarkPointer` is rendered inline, just before the first evidence mark. The
arrow and tick are `position: absolute` with no `top`, so each keeps the
vertical position of the line where the mark starts. CSS places them; nothing
is measured.
- **Arrow:** a solid ink triangle (10 × 12px). It sits at `left: calc(2.25rem + 5px)`, centred in the 20px gutter between the paragraph number and the text, and vertically centred on the line (`margin-top: calc(0.5lh - 6px)`).
- **Tick:** an 18px circle-check (accepted) or circle-x (rejected), stroke 2.25, on a paper disc at the shoulder's left edge. Pending shows nothing. It is hidden from assistive technology because the decision bar states the decision in words.
- **Motion:** when the selected finding changes, the arrow and tick travel from the line they left to the new mark: a 180ms `cubic-bezier(0.16, 1, 0.3, 1)` transform (FLIP) that ends at the CSS position, so the resting place never depends on a measurement (MarkPointer.tsx). On a new decision the tick plays `settle` (180ms, same curve, from `translateY(-6px) scale(0.9)` at 0.4 opacity). Under `prefers-reduced-motion: reduce` the travel is skipped and every CSS animation and transition drops to 0.01ms.

### Evidence marks
- **Quote:** highlight wash plus a 2px ink underline, with a 1px radius.
- **Obligation without a located quote:** a 1.5px dotted slate-soft underline.
- **Quote not located:** the quoted text, set in Charis and struck through in crimson, inside the verdict plate.

### Verdict plate
A double-ruled plate in the impact's own ink and tint. It shows the impact
word as the verdict heading, then "Machine interpretation · <provider>", the
meaning of the impact, and the rationale (16px). A rule in the impact ink
precedes a definition list. *Quote check* (status icon, word and detail) is a
row of its own, separate from the verdict. The *Score* row reads "Term overlap
n (rule score)" for the deterministic judge, or "Model-stated n,
uncalibrated". It is never a percentage or a High/Medium/Low badge.

### Findings index and impact legend
- **Legend:** a neutral plate titled "Impact" in guide words. Each impact tag is paired with its count and is a toggle button (`aria-pressed`) that filters the index. A zero count is inert.
- **Index:** a listbox (arrow keys, Home and End), grouped by obligation. Each group's headword is the obligation, clamped to two lines, with its paragraph number in the shoulder. Each entry shows the clause (Charis 16px bold), an impact tag, the quote status in words, and the decision. The selected entry gets a raised background, an underline, the shoulder arrow and the decision glyph.
- **Picker (below 1440px):** a select with optgroups per obligation, plus previous and next icon buttons.

### Decision bar
A 1.5px ink rule, then "Your decision" with the current `DecisionMark` (icon,
word and decided-at time), then Accept, Reject and, once decided, a quiet
Clear button. The mark changes only after the server confirms. A failure
shows an error notice with Try again and keeps the last saved decision. The
result is announced in a polite live region.

### Notices and states
A single-ruled box: icon, a bold title, a 13px cause, and a recovery action on
the right. The tones are info, warning, error and unavailable (slate soft on
paper). The skeleton shows 12px rule-coloured bars and appears only after
300ms. An empty state has a Charis 18px title with a slash-circle icon and
says what to do next.

### Tables
Dense and rule-separated. A 1.5px ink header rule, 1px rule rows, 8px cell
padding, flush first and last columns, top-aligned cells, and right-aligned
numbers.

### Navigation
The top bar is ink, with the Charis wordmark and six routes: Overview,
Circulars, Search, Assessments, Point in time, Evaluation. Routes are 14px
medium. Inactive routes are bar muted. The active route is bar bright with a
3px inset underline. Below 768px a 40px menu button opens a stacked list,
which closes on Escape or on navigation and returns focus to the button. A
skip link comes first.

## Do's and Don'ts

### Do:
- **Do** put source text in Charis `.doc-text` inside a leaf, with numbers in a 2.25rem shoulder.
- **Do** name what a leaf shows with a `GuideHead` (first, title, last) rather than a label above a heading.
- **Do** put any interpretation that carries colour inside a double-ruled `Plate`, with the word beside the colour.
- **Do** keep quote status, machine interpretation and analyst decision as three separate, labelled states with an icon each.
- **Do** label synthetic and fictional material with `SyntheticTag` wherever it appears.
- **Do** step tone (desk #E2DED4, paper #FAF8F3, raised #FFFFFF) to separate surfaces.
- **Do** keep secondary text in slate soft (#56606E). It holds 4.75:1 on desk and 6.01:1 on paper.
- **Do** keep selection and filters in the URL so a refresh or shared link restores them.

### Don't:
- **Don't** use slate faint (#7A8391) or rule (#D9D4C8) for text.
- **Don't** use impact ink outside a plate, tag or notice, or without its word.
- **Don't** add shadows to leaves, plates or panels. Box-shadow draws rules here, and the tooltip is the only floating layer.
- **Don't** round leaves, plates, tags or notices.
- **Don't** set any text below 12px, or use small caps anywhere except guide words.
- **Don't** position the shoulder arrow or tick by measuring layout, and don't animate the arrow.
- **Don't** add entrance animations. The arrow's travel and the tick's settle-in are the only authored motions.
- **Don't** show a model score as a percentage or a confidence badge, or show an unknown value as zero.
- **Don't** ship a dark theme unless every state, contrast pair and chart has been verified in it.
