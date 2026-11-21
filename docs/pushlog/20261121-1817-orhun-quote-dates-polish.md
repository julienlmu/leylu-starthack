# Quote wording: the flight leaves the day after the ready date; a town without postcode is named
- Who: Orhun (tool: Claude Code)
- Branch: orhun/quote-dates-polish
- What changed:
  - agent/quote_style.py: port-to-port too, the flight leaves the day after the ready date (R23 said "leaves on 24 November" for goods ready on 24 November); "Bonn, Germany" / "Augsburg" pickups are named ("we collect them in Bonn"), placeholders are not
- Files touched: agent/quote_style.py, agent/test_quote_style.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: agent 336 passed (18 xfailed, Julien's trap suite), backend 69 passed
- Heads-up for teammates: none
