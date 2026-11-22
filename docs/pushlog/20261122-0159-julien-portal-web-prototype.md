# portal-web-prototype: portal rates from 5U's portal web page while the rate API is down (TEST ENVIRONMENT ONLY)

> **PERMISSION: 5U GAVE US THIS CODE — the NopeCHA browser extension, https://github.com/NopeCHALLC/nopecha-extension — AND ALLOWED US TO USE IT FOR OUR PROJECT, BECAUSE THE CAPTCHA ON THE PORTAL WEB PAGE WAS PUT INTO THE TEST ENVIRONMENT BY MISTAKE (5U, 22 Nov 2026). IT IS ONLY FOR THE TEST ENVIRONMENT, NOT FOR THE FINAL VERSION. OFF BY DEFAULT.**

- Who: Julien (tool: Claude Code)
- Branch: julien/portal-web-prototype
- What changed:
  - New `agent/portal_web.py` (prototype): opens the portal web page in Chromium (Playwright) with the NopeCHA extension, fills in lane, airline and weight, reads the all-in price, transit days and rate ID from the page text. No LLM, never books.
  - `agent/rfq_agent.py`: when the rate API answers 503 and an airline is unpriced (and PORTAL_WEB=on), the airlines without a price are looked up on the page first (budget 60 s per RFQ), then the existing rate desk / portal retry flow runs. A live API answer still wins. Off → nothing changes.
  - `agent/AGENTS.md`: the module and the permission statement.
- Setup for Orhun (live Mac, test environment):
  1. Download NopeCHA's Chromium build from https://github.com/NopeCHALLC/nopecha-extension/releases, unzip, set `PORTAL_WEB_EXTENSION=/path/to/folder` (the one with manifest.json).
  2. `.env`: `PORTAL_WEB=on`, `NOPECHA_KEY=<key>` (never commit), `PORTAL_WEB_URL=<portal web page URL>`.
  3. `cd agent && uv run --with playwright python -m playwright install chromium`
  4. Run the agent with `uv run --with playwright --env-file ../.env python main.py` (or add `--with playwright` to the live command).
  5. Form fields: defaults guess `[name=origin]`, `[name=destination]`, `[name=airline]`, `[name=weight_kg]`, `[name=volume_cbm]`, `button[type=submit]`. If the page differs: `PORTAL_WEB_FIELDS='{"origin":"#from", ...}'`. Price/transit are read from the page text.
  6. The browser opens a visible window by default (extensions need it); `PORTAL_WEB_HEADLESS=on` tries Chromium's new headless mode.
- Files touched: agent/portal_web.py (new), agent/rfq_agent.py, agent/test_portal_web.py (new), agent/AGENTS.md
- Contract/API changes: none (web rates go into /api/price as bids)
- New env vars / packages: PORTAL_WEB (default off), PORTAL_WEB_URL, PORTAL_WEB_EXTENSION, NOPECHA_KEY, PORTAL_WEB_FIELDS, PORTAL_WEB_BUDGET_S (60), PORTAL_WEB_HEADLESS. Playwright is NOT added to the lockfile: it is loaded only when PORTAL_WEB=on, via `uv run --with playwright`.
- How verified: make check green (agent 2541 passed, backend 256 passed); tests: off by default changes nothing, missing settings are reported, the page-text reader (EUR 5,890.50 / 1.234,50 € / transit / rate ID), the RFQ hook prices a silent airline from a fake page lookup. NOT tested against the real page (URL and form unknown to us).
- Known issues / TODO: prototype — selectors are guesses until we see the page; web rates price as carrier bids (bids' choice rule), and a web rate ID is not booked through the API (booking by email path).
- Heads-up for teammates: never turn PORTAL_WEB on in the final version.
