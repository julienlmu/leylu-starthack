# Door-to-port: origin airport from the pickup zone when the RFQ names only the pickup address
- Who: Orhun (tool: Claude Code)
- Branch: orhun/agent-door-to-port
- What changed: agent/extract.py to_rfq() takes the origin airport from the pickup postcode (backend/data/pickup_zones.csv) for door-to-port RFQs; the first live RFQ (#269, Bergisch Gladbach → ORD, no airport named) was handed to a person as "missing: origin"
- Files touched: agent/extract.py, agent/test_rfq_agent.py
- Contract/API changes: none (the backend already resolves the zone; now the agent does too, before the carrier round)
- New env vars / packages: none
- How verified: cd agent && uv run pytest -q → 65 passed (new test: 51447 Bergisch Gladbach → CGN, a Frankfurt pickup overrides a different origin)
- Known issues / TODO: none
- Heads-up for teammates: Julien, small change in your extract.py, please review
