---
version: 1
slug: "app-page-tsx"
primary_target: "app/page.tsx"
related_targets: ["components"]
---

# Sessions UI

Scope: the Sessions screen (`app/page.tsx`), the whole operator surface. Mode: Operate.
Audience/job: night-watch operator finds the session that needs a person and understands what the agent did; jury reads it on a projector in a 3-minute pitch.
Constraints: `lib/types.ts` contract fixed; mock fallback must keep working; desktop first, holds at 768px.
Room reserved (not built): live step streaming, pause/resume + hand-written reply, CRM dashboard.
Decided unattended (subagent run, no interview possible): light theme from the projector scene; direction = assigned roll.

## Direction contract

THESIS: The session list is a flight-progress-strip rack. Each session is a printed strip in a coloured holder; the strips that need a person are cocked out of line, the way a controller flags a strip for action. Refuses the grey admin table with pill badges and the dark neon ops dashboard.

OWN-WORLD: Cool blue-grey strip board, deep console-slate top bar, near-white strip paper with 1px hairline field boxes and tiny condensed caps captions. Stage = flat holder colour field (blue new, yellow pricing, lilac quoted, green booked, teal tracking, grey done, slate failed). Signal red reserved for needs-a-person and errors; diagonal hatch for paused. Barlow / Barlow Condensed, tabular figures; mono only for rate IDs, AWB, addresses of mail.

STORY: The operator sees at once how many sessions need a person, which strip it is, and opens it; the detail tells, in order: who, what state, did we hit 2:00 / price / cost, what was asked, what we answered, every agent step and its cost.

FIRST VIEWPORT: Top bar (wordmark, Sessions, red needs-a-person counter, LIVE/MOCK source). Left 400px rack: search, stage filter row with counts, strips (holder cell with #id, customer, route, time box, price). Right: session head (#id large, customer, stage track, state banner), three scored readings at scale (response vs 2:00 on a 0–6:00 scale, all-in price, LLM cost vs $0.10), then request field strip, thread + timeline, prices + booking.

FORM: assigned candidate 3 of 7 (flight progress strips); seed:a16617537902bcee. Raises: scale contrast carries hierarchy (variable-font-specimen); one 1px hairline weight everywhere (design-annual plate section); colour as flat fields that own areas, not tinted pills (zoo guide map); the session number is the index, navigable in strict sequence with j/k (Saville catalog); timeline dots on a fixed magnitude ramp, the item under the eye ringed in red when it needs a person (star atlas).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
