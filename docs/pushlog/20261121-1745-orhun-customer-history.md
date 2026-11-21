# No pickup address and no city: use the same customer's last pickup (round 16)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/customer-history
- What changed: round 16 (17:32, nordlicht-audio, "truck pickup from our warehouse" to PVG, no address, no city, no airport) was handed over as "missing: origin". The same customer picked up in 36627 Fulda in round 9. When the origin is missing, agent/rfq_agent.py now takes the customer's last pickup address with a known zone from the CRM (door-to-port; origin = that zone's airport) or the last departure airport (airport delivery), and logs it
- Files touched: agent/rfq_agent.py, agent/test_rfq_agent.py
- Contract/API changes: none (uses GET /api/sessions)
- New env vars / packages: none
- How verified: agent 148 passed (new: nordlicht-audio → Fulda, FRA; a new customer → nothing)
- Known issues / TODO: a customer with no history still needs a person (or a question back)
