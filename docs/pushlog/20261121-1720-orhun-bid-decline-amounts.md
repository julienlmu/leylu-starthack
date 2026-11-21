# Bids: a decline that still names an amount goes to the LLM (fix on #61)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/bid-decline-free
- What changed: read_bid() skips the LLM for a decline only when the reply holds no money amount. "We cannot offer a direct flight. Option A: EUR 2,450 ... Option B: EUR 1,980" was dropped as "no offer" (parse_bid can't pick between two amounts), which could lose the winning bid; plain declines ("we don't serve pickup zone 51") stay free
- Files touched: agent/bids.py, agent/test_bids.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: cd agent && uv run pytest -q → 132 passed (new test fails on the previous code)
- Known issues / TODO: none
- Heads-up for teammates: none
