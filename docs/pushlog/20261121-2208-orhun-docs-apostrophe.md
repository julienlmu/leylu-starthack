# A document promise with a curly apostrophe ("We’ll send …") is still a promise (R63)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/docs-promise-apostrophe
- What changed: agent/booking_agent.py DOCS_PROMISE matches will/’ll/'ll send|forward|provide; R63 "We’ll send you the dangerous goods documents shortly" went to a person.
- How verified: agent 1267 passed (R63, R40 and R39 wordings)
- Review: the will/’ll send|forward|provide alternative is grouped with the document words ("I'll forward your offer to my manager", "We will send the purchase order", "We'll provide the pickup address" no longer count as a promise).
