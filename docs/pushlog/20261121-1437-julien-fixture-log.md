# Agent: local runs print the mails they would send
- Who: Julien (tool: Claude Code)
- Branch: julien/fixture-mail-log
- What changed: FixtureMailbox (MOCK=1) prints every mail it would send ("[not sent] to …"), so a local run shows bid requests and the quote
- Files touched: agent/inbox.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: `cd agent && uv run pytest -q` → 38 passed. Full local run against the live 5U gateway + live portal (throwaway in-memory stand-in for the backend, not committed): German RFQ MUC→ORD → extracted for $0.000123 → 2 bid requests → cut-off → portal price Xenon Cargo EUR 1,308.21 → quote in thread, 8 s end to end
- Known issues / TODO: none
- Heads-up for teammates: Orhun — the portal allows only 10 rate reads per minute per team (X-RateLimit-Limit: 10); chargeable weight = max(kg, m³ × 167); lanes come from GET /v1/portal/ports (MUC has no JFK lane, ORD yes)
