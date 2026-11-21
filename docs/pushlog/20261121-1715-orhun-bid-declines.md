# Bids: carrier declines never reach the LLM (55% of our gateway spend)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/bid-decline-free
- What changed: agent/bids.py read_bid() returns "no offer" for free when the regex finds no bid and the reply declines ("we do not serve this lane / zone", "cannot offer", "no capacity", "regret", …) or contains no number at all. Before, every such decline went to gpt-6-luna (~$0.00004 each); the analysis thread measured them at 55% of our spend, and cost points are 40 per accepted quote on a steep scale
- Files touched: agent/bids.py, agent/test_bids.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: agent 131 passed (new: four decline wordings with the LLM patched to fail)
- Known issues / TODO: asking only airlines whose lanes cover the route would cut the declines themselves
- Heads-up for teammates: Julien, small change in bids.py
