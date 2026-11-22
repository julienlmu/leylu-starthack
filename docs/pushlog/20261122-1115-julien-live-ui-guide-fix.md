# live-ui-guide-fix: every guide step highlights its feature (branch only, not deployed)
- Who: Julien (tool: Claude Code)
- Branch: julien/live-ui-upgrade (draft PR #311, do not merge)
- What changed: the guide never switched views, so steps 5-8 (Simple view) and 9-19 (Detailed view) found no element when the other view was open and showed a centred card without a highlight. Each step now names its view; the guide switches to it, waits up to ~1 s for the element to render, scrolls it into view and rings it. The guide still starts only from the Guide button.
- Files touched: frontend/components/guide.tsx, frontend/components/top-bar.tsx
- Contract/API changes: none
- New env vars / packages: none
- How verified: eslint + tsc clean; clicked through all 21 steps in headless Chrome on :3755: the view switches at step 5 (Simple) and step 9 (Detailed), steps 7, 13 and 19 checked by screenshot with the feature highlighted
- Known issues / TODO: the Booking step highlights the empty "Not booked" box when the selected request has no booking yet
- Heads-up for teammates: branch only, live untouched
