# portal-memory: price a failed portal from its earlier answers (R93/R94/R95 portal 503)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/portal-cache
- What changed:
  - When a lane airline's portal rate call fails (5xx, network, 429), /api/price adds a `source: "portal"` option for it from the portal's newest earlier answer for the same lane and airline in the CRM ("priced" events), scaled per kg. It uses the same weight bracket (the airline's breaks); otherwise the nearest billed weight within ×0.5–×2, flagged `remembered: "nearest"`. The option has no rate ID, so booking books a fresh rate, or by email while the portal is down.
  - Pickup and insurance are taken out of the remembered all-in. Multi-lot and alias events, and remembered options themselves, are never used. A live answer always wins.
  - The "portal: …" note stays, so the agent's PORTAL_RETRY and RATEDESK still run. A remembered rate replaces only the sheet as the last resort.
  - The 503 body is logged up to 600 characters (it was 120/200).
- Files touched: backend/portal_memory.py (new), backend/pricing.py, backend/portal.py, backend/app.py, backend/test_portal_memory.py
- Contract/API changes: price options may carry `remembered` ("bracket" | "nearest"); optional field
- New env vars / packages: PORTAL_MEMORY (default on; off = as before)
- How verified: backend 252 passed (9 new in test_portal_memory.py), agent 2524 passed
- Known issues / TODO: coverage depends on what the CRM priced earlier; a lane never priced while the portal was up gets nothing
- Heads-up for teammates: Portal.down {code: time} marks airlines whose last rate call failed

## Second push: T+0 portal probe (PORTAL_PROBE)
- The agent prices once without bids right after extraction, in a background thread while the carriers are asked. If the portal fails, the needs_human ntfy push with the web-form inputs goes out at T+0 instead of after the 90 s cut-off, giving a person ~4 minutes instead of ~2. The retry after the cut-off doesn't push the same form again.
- The backend's "portal: …" note now ends with "(lane airlines: GN, MD)", so the form line lists every portal airline on the lane, not only the last one that failed.
- Files: agent/rfq_agent.py, agent/conftest.py (probe off in the other tests: their fake APIs hand out price results in order), agent/test_portal_probe.py, backend/pricing.py
- Switch: PORTAL_PROBE (default on; off = as before)
- Verified: agent 2527 passed, backend 252 passed

## Third push: one-step human portal rate (portal_helper.user.js + POST /api/sessions/{id}/portal-rate)
- The push now starts with a prefilled portal link (`…/portal/ui#s=41&o=FRA&d=LAX&w=300&v=1.1&a=MD,GN`). The airlines are ordered so the likely winner for the ask comes first (from the portal memory: fastest transit or cheapest per kg).
- agent/portal_helper.user.js (Tampermonkey):
  - closes the ad pop-ups by their X (never the ad button) and takes "Necessary only" on the cookie wall
  - prefills the fields by kind and label (they shuffle) and puts the cursor in the sum box; a person types the sum and presses Enter
  - posts the "Your rate" block to the local backend, then moves on to the next airline
  - it never reads or fills the sum; the key field is left to the browser's autofill
  - a bookmarklet build (no auto-send; it shows the portal_rate.py line) is in /mnt/project-files/portal/
- backend: `POST /api/sessions/{id}/portal-rate {airline, text}` → portal_paste.parse → a manual_portal bid (deduplicated) + "bid" event
- agent: portal rates typed during the bid round are merged before the agent writes its bids (they were overwritten), and they skip the rate desk round. A rate typed while the desk is asked is priced at once.
- Verified: agent 2529 passed, backend 255 passed. The userscript and the bookmarklet were tested in headless Chromium against the saved portal_ui.html with a mocked portal: shuffled fields prefilled, a forced ad closed by its X (CTA untouched), the typed sum submitted, "Your rate" posted, the next airline prefilled.
