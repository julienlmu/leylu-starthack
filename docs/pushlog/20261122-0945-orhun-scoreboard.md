# scoreboard: Scoreboard tab with estimated points per round (DO NOT MERGE during the live run)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/scoreboard-tab
- What changed:
  - New `/scoreboard` page and a "Scoreboard" nav tab next to Dashboard.
  - Estimated points per 6-minute round (accuracy 45, speed 15, LLM cost 40, tracking 10), where points leak, per-round table.
  - Computed in the browser from `/api/sessions`; Sessions and Dashboard pages unchanged.
- Files touched: frontend/lib/score.ts, frontend/app/scoreboard/page.tsx, frontend/components/top-bar.tsx
- Contract/API changes: none
- New env vars / packages: none
- How verified: pnpm lint, tsc --noEmit, pnpm build all pass (in the cloud, not on the live Mac); page checked with mock data.
- Known issues / TODO: points are an estimate (won = accurate); real verdicts are on 5U /v1/board/me, which the UI does not call.
- Heads-up for teammates: frontend is Batu's folder; Orhun asked for this. Keep out of main until the live run is over.

## Update 09:45 → 09:50: dark console theme
- Whole UI switched to a dark palette by overriding the colour tokens in one block at the end of `:root` in `frontend/app/globals.css` (delete that block to go back). Stage holder colours unchanged.
- Two light-only fills adjusted for dark: quoted row in `components/detail/prices.tsx`, outcome pills on the Scoreboard.
- Verified: lint, tsc, build pass; Sessions, session detail, Dashboard and Scoreboard checked with mock data.
