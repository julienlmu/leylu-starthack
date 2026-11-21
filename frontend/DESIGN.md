---
name: Leylü Forwarder
description: Sessions console for an autonomous air-freight forwarder, built as a flight-progress-strip rack.
colors:
  console: "oklch(0.255 0.04 256)"
  console-2: "oklch(0.32 0.045 256)"
  console-ink: "oklch(0.97 0.008 250)"
  console-ink-2: "oklch(0.78 0.025 252)"
  board: "oklch(0.925 0.014 248)"
  board-2: "oklch(0.885 0.018 248)"
  paper: "oklch(0.993 0.003 250)"
  paper-2: "oklch(0.968 0.008 250)"
  ours: "oklch(0.955 0.016 256)"
  ink: "oklch(0.2 0.03 258)"
  ink-2: "oklch(0.43 0.03 256)"
  ink-3: "oklch(0.56 0.025 254)"
  rule: "oklch(0.86 0.014 250)"
  rule-strong: "oklch(0.72 0.02 252)"
  st-new: "oklch(0.6 0.15 252)"
  st-new-ink: "oklch(0.99 0.005 250)"
  st-pricing: "oklch(0.87 0.135 92)"
  st-pricing-ink: "oklch(0.27 0.05 80)"
  st-quoted: "oklch(0.78 0.09 300)"
  st-quoted-ink: "oklch(0.24 0.06 300)"
  st-booked: "oklch(0.8 0.12 155)"
  st-booked-ink: "oklch(0.24 0.06 160)"
  st-tracking: "oklch(0.8 0.08 205)"
  st-tracking-ink: "oklch(0.24 0.05 215)"
  st-done: "oklch(0.87 0.012 250)"
  st-done-ink: "oklch(0.3 0.025 256)"
  st-failed: "oklch(0.38 0.03 256)"
  st-failed-ink: "oklch(0.97 0.006 250)"
  signal: "oklch(0.56 0.205 27)"
  signal-ink: "oklch(0.99 0.004 30)"
  signal-wash: "oklch(0.965 0.025 25)"
  signal-text: "oklch(0.48 0.18 27)"
  ok: "oklch(0.52 0.13 155)"
  late: "oklch(0.6 0.15 65)"
  late-text: "oklch(0.5 0.13 60)"
typography:
  display-index:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 700
    lineHeight: 1
    fontFeature: "\"tnum\" 1"
  display-reading:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "2.5rem"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.025em"
    fontFeature: "\"tnum\" 1"
  headline:
    fontFamily: "Barlow, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  strip-index:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1
    fontFeature: "\"tnum\" 1"
  title:
    fontFamily: "Barlow, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Barlow, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.625
    fontFeature: "\"tnum\" 1"
  body-sm:
    fontFamily: "Barlow, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.43
  code:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.33
  caption:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.06em"
rounded:
  xs: "2px"
  sm: "2px"
  md: "4px"
spacing:
  hairline: "1px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  section: "32px"
components:
  strip:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
  strip-holder-pricing:
    backgroundColor: "{colors.st-pricing}"
    textColor: "{colors.st-pricing-ink}"
    typography: "{typography.strip-index}"
    width: "3.5rem"
  strip-holder-person:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.signal-ink}"
    typography: "{typography.strip-index}"
    width: "3.5rem"
  button-person-queue:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.signal-ink}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "36px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "32px"
  chip-filter:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.sm}"
    padding: "0 6px"
    height: "28px"
  chip-filter-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
  chip-filter-alert:
    backgroundColor: "{colors.signal-wash}"
    textColor: "{colors.signal-text}"
    rounded: "{rounded.sm}"
  input-search:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "40px"
  field-box:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "10px 12px"
  top-bar:
    backgroundColor: "{colors.console}"
    textColor: "{colors.console-ink}"
    height: "56px"
---

# Design System: Leylü Forwarder

## Overview

**Creative North Star: "The Strip Rack"**

The whole surface is an air-traffic flight-progress-strip board. Every session is a printed strip of near-white paper sitting in a flat coloured holder on a cool blue-grey board, under a deep console-slate bar. Strips that need a person are cocked out of line, the way a controller pulls a strip for action. The screen is read at 2 a.m. on a laptop and on a projector, so the ground is light on purpose, the hierarchy is carried by scale contrast, and numbers are always tabular.

Density is high but orderly: fields share one 1px hairline the way boxes are printed on a strip, each box carrying a tiny condensed-caps caption and its value under it. Colour comes in flat fields that own whole areas (a holder cell, a stage box, a banner), never as tinted pills. Signal red has one meaning. The session number is the index: large, condensed, and navigable in sequence.

The world rejects the grey admin table with pill badges and the dark neon ops dashboard.

**Key Characteristics:**
- Light board, paper strips, slate console bar.
- Stage shown as a flat holder field, one colour per stage.
- Signal red reserved for "needs a person" and errors.
- One hairline weight (1px) everywhere; field grids drawn by 1px gaps over the rule colour.
- Barlow / Barlow Condensed with tabular figures; mono only for machine strings.
- One authored motion: the cocked strip sliding out of line.

## Colors

A cool blue-grey ground with flat, mid-chroma stage fields and a single hot signal; the project's canonical format is OKLCH, defined as custom properties in `app/globals.css`.

### Primary
- **Console Slate** (console): the top bar and the "Leylü" sender tag on our own mails. The deep anchor of the screen; also the shadcn `primary`.
- **Console Raised** (console-2): inactive controls sitting on the console bar.
- **Console Ink / Console Ink Dim** (console-ink, console-ink-2): text on the console; the dim one for secondary labels and tally captions.

### Secondary: stage holders
Each stage is a field colour plus the ink that reads on it, applied through `data-stage` so strips, the stage track and filter swatches share one source.
- **Departure Blue** (st-new / st-new-ink): new sessions; also the customer sender tag, the search caret and focus border, and "decision" marks in the timeline.
- **Strip Yellow** (st-pricing / st-pricing-ink): pricing; also the active-nav underline and text selection.
- **Quote Lilac** (st-quoted / st-quoted-ink): quoted; also the "quoted" tag in the price table.
- **Runway Green** (st-booked / st-booked-ink): booked; also the live-source badge.
- **Tracking Teal** (st-tracking / st-tracking-ink): tracking.
- **Archive Grey** (st-done / st-done-ink): done.
- **Failed Slate** (st-failed / st-failed-ink): failed.

### Tertiary: signal and pace
- **Signal Red** (signal / signal-ink): needs-a-person holders, the person-queue counter, the needs-a-person banner, alert timeline marks. Applied with `data-person="true"`, which overrides the stage holder.
- **Signal Wash / Signal Text** (signal-wash, signal-text): the quieter alert register: alert filter chip, alert field boxes, reason lines, dangerous-goods flags.
- **On-Target Green** (ok): response times inside 2:00, "lowest" price, won outcome.
- **Late Amber / Late Text** (late, late-text): response times over target and LLM cost at or past the zero-points line.

### Neutral
- **Board / Board Deep** (board, board-2): the rack ground behind the strips; body background.
- **Strip Paper** (paper): strips, field boxes, inputs, cards.
- **Paper Shade** (paper-2): the detail pane ground, table header rows, empty scale tracks.
- **Our Paper** (ours): background of mails we sent, so our replies read apart from the customer's.
- **Ink / Ink Mid / Ink Faint** (ink, ink-2, ink-3): primary text, secondary text, captions and absent values.
- **Rule / Rule Strong** (rule, rule-strong): the 1px hairline; the strong one for inputs, unfilled stage boxes, dashed empty states and the timeline spine.

### Named Rules
**The One Signal Rule.** Signal red means "a person must act" or "error", nothing else. No decorative red, no red for "late" (late is amber).

**The Flat Holder Rule.** Stage colour is a flat field that owns an area (holder cell, stage box, 10px swatch). Never a tinted pill, never a gradient, never text coloured in a stage hue on paper.

## Typography

**Display Font:** Barlow Condensed (sans-serif fallback)
**Body Font:** Barlow (sans-serif fallback)
**Label/Mono Font:** JetBrains Mono, for thread IDs, mail addresses and rate IDs only

**Character:** An instrument-panel pairing: Barlow Condensed for indexes, readings and captions, the way strip printers set figures; Barlow for names and prose. Tabular figures are on globally (`font-feature-settings: "tnum" 1`).

### Hierarchy
- **Display index** (700, 2.75rem, 1): the session number in the detail head, inside its holder block.
- **Display reading** (700, 2.5rem, 1, tight): the three scored readings (response time, all-in price, LLM cost). Only real numbers get this size; absent values drop to a 1.25rem ink-3 line.
- **Headline** (600, 1.75rem, 1.25, tight, balanced): the customer name in the session head; the page's h1.
- **Strip index** (700, 1.375rem, 1): the #id in each strip's holder cell.
- **Title** (600, 1rem): section headings (Request, Mail thread, Agent steps, Price options, Booking).
- **Body** (400–600, 0.9375rem): customer names on strips, field values, mail bodies (leading 1.625, max 68ch).
- **Body small** (0.875rem / 0.8125rem): notes under readings, strip meta lines, timeline text, tables.
- **Caption** (600, 0.6875rem, 0.06em, uppercase, Barlow Condensed, ink-3): the label printed in the corner of every field box, reading, table header and timeline step. Route codes use condensed 700 at 0.875rem with wide tracking.

### Named Rules
**The Scale Carries Rank Rule.** Hierarchy comes from size jumps (0.6875 → 0.9375 → 1.75 → 2.75rem), not from colour or boxes. Display sizes are reserved for indexes and scored numbers.

**The Machine String Rule.** Mono is only for strings a machine produced (thread ID, address, rate ID, AWB). Everything a person reads is Barlow.

## Layout

Two panes under a 56px console bar. The rack is a fixed column on the left (21rem from 768px, 28rem from 1280px) on the board ground, with search and filters pinned above a scrolling list of strips (8px apart, 12px left / 20px right padding so cocked strips have room to slide). The detail pane fills the rest on paper-2, scrolls on its own, and centres its content up to 96rem with 20–32px side padding and 32px between sections.

Inside the detail, two-column grids (1.15fr / 1fr) pair the mail thread with agent steps and prices with booking from the 56rem container width; the scoreboard becomes three columns from 42rem. Below 768px the panes stack: the rack caps at 26rem tall above the detail, and the top bar drops the "Forwarder" word, the nav and the tally. Container queries, not viewport queries, drive strip and chip density (the time box appears from a 26rem rack).

Spacing steps observed: 1px hairline gaps, 4, 8, 12, 16, 20, 32px. Field boxes pad 10px × 12px; readings 12/16px.

## Elevation & Depth

Mostly flat and tonal: board, paper-2 and paper separate the planes. The only shadows live on strips, which are physical objects in the rack: a hairline lift at rest and a deeper drop when a strip is selected (with a 2px ink ring). Nothing else casts a shadow.

### Shadow Vocabulary
- **Strip at rest** (`box-shadow: 0 1px 0 oklch(0.2 0.03 258 / 0.08), 0 1px 3px oklch(0.2 0.03 258 / 0.06)`): every strip in the rack.
- **Strip selected** (`box-shadow: 0 6px 16px -4px oklch(0.2 0.03 258 / 0.28)`): the open strip, together with a 2px ink ring.

### Named Rules
**The Only Strips Lift Rule.** Shadows belong to strips. Panels, field grids, banners and tables stay flat and are separated by hairlines and tone.

## Shapes

Nearly square. The base radius is 4px (`--radius: 0.25rem`); swatches, tags and scale tracks use 2px; the `/` key hint 3px. Field grids are drawn as a rule-coloured container with 1px gaps between paper cells, so every box shares one hairline. Paused sessions carry a diagonal hatch (2px stroke, 7px period, -45°, in currentColor at 22%) over their holder. Empty states are dashed rule-strong boxes. The mark is two offset strip rectangles, yellow over red.

## Components

### Strips (signature)
A printed strip in its holder: the defining component.
- **Grid:** holder cell (3.5rem) · customer + route + meta · time box (3.5rem, from a 26rem rack) · carrier + price (5rem), divided by 1px rule lines.
- **Holder:** flat stage field with the #id (strip index type) and stage caption in the holder ink; signal red when it needs a person; hatched when paused.
- **States:** hover nudges 2px right; a needs-a-person strip sits 12px out of line and slides there once on load (`cock`, 520ms, `cubic-bezier(0.16, 1, 0.3, 1)`, 120ms delay); selected gets a 2px ink ring and the deep shadow. Closed outcomes strike through the price.

### Stage Track
A row of equal boxes sharing hairlines, one per stage, condensed caps. The current box takes the stage field; passed boxes keep a 10px swatch of their holder colour; future boxes show an empty rule-strong square.

### Readings (Scoreboard)
Three cells in a hairline grid: caption, display-reading number in ok / late-text / ink, a one-line note, and a 10px scale bar (0–6:00 with a green zone to 2:00 then a yellow-to-red ramp; cost filled in ink against the $0.10 line) with a 3px needle.

### Field Strips
Hairline grid of field boxes: caption on top, 0.9375rem medium value below. The alert variant fills with signal-wash and sets caption and value in signal-text.

### Buttons
- **Shape:** gently squared (4px).
- **Person queue:** signal field with signal ink, 36px tall, a condensed bold count before the label; falls to console-2 with dim ink when the count is zero; pressed state adds a 2px console-ink ring offset on the console.
- **Secondary:** paper with a rule-strong border, 32px, hover to paper-2.
- **Focus:** 2px Departure Blue outline at 2px offset, globally.

### Chips (stage filters)
- **Style:** 28px, 4px radius, rule-strong border on translucent paper, label left, condensed count right, a 10px holder swatch when the rack is wide enough.
- **State:** active inverts to ink field with paper text; the person chip spans the row at 32px and turns signal-wash / signal-text with a signal border when the count is above zero; zero-count chips drop to 60% opacity.

### Inputs / Fields
- **Style:** 40px search field, paper, rule-strong border, 4px radius, leading search icon, `/` key hint on the right.
- **Focus:** border shifts to Departure Blue; caret is Departure Blue.

### Navigation
The console bar: mark + "Leylü" (700) + "Forwarder" (condensed 500, dim), one condensed-caps "Sessions" item with a 3px Strip Yellow underline when current, a tally of tonight's numbers (caption labels, semibold values) from 1280px, the person-queue button, and a source badge (Runway Green with a pinging dot when live, Strip Yellow when on mock data).

### Mail Thread
Mails as bordered cards: customer mails on paper, ours on Our Paper and indented from the other side at wide widths. A header row carries a solid sender tag (Departure Blue for the customer, Console Slate for Leylü), the mono from/to line and the time.

### Agent Timeline
Time and offset · spine with a mark · caption + text · per-step cost. Marks follow a fixed magnitude ramp: mail 12px ink dot, decision 10px blue dot, internal step 8px hollow ring, alert 12px signal dot with a 4px signal ring. Cost of $0 shows in ink-3.

## Do's and Don'ts

### Do:
- **Do** show stage as a flat holder field set by `data-stage`, and override it with signal via `data-person="true"`.
- **Do** draw grouped data as hairline field grids: rule container, 1px gaps, paper cells, caption over value.
- **Do** set every number tabular, and put indexes and scored readings in Barlow Condensed 700.
- **Do** keep absent values at caption-to-body scale in ink-3 so display size only carries real numbers.
- **Do** read colours from the custom properties in `app/globals.css`; add a token there before using a new colour twice.
- **Do** hatch paused holders rather than recolouring them.

### Don't:
- **Don't** use signal red for anything except "needs a person" and errors.
- **Don't** put stage colour in tinted pills or as coloured text on paper.
- **Don't** add shadows to panels, tables or banners; only strips lift.
- **Don't** add motion beyond the strip cock and short state transitions (150–200ms); respect reduced motion.
- **Don't** use mono for prose, names or headings.
- **Don't** introduce a dark theme or neon accents; the board is light for the projector.
