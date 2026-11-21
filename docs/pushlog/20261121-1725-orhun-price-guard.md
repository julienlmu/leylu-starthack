# Price guard before the quote goes out (SCORE_ANALYSIS R1)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/price-guard
- What changed: /api/price adds "warnings" (and "CHECK: …" in why, shown in the Sessions UI) when: a door-to-port quote has no pickup leg; the charged weight is below max(actual, cbm × 167); fewer sheet/portal sources priced than the lane has (portal 429/503/slow); the chosen EUR/kg is outside 0.5×–2× the lane's sheet range. It never blocks a quote: an answer always beats none
- Files touched: backend/pricing.py, backend/test_pricing.py
- Contract/API changes: /api/price response gains "warnings": [string]
- New env vars / packages: none
- How verified: backend 63 passed (new: offline portal → a sources warning, still quoted; all sources priced → no warning)
