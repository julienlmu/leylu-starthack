# Airlines the customer rules out are never quoted (R42 excluded_airline)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/excluded-airline
- What changed: agent/exclusions.py finds "do not offer/use/book ... <airline name> (XX)" sentences, remembers them per customer address (excluded_airlines.json), rfq.excluded_airlines; those airlines are not asked for bids and backend/pricing.py drops their options before choosing. EXCLUSIONS=off switches it off.
- How verified: agent 366, backend 74 passed (R42's exact sentence, code-only (ZS), per-customer memory, pricing picks the next airline)
