# A document promise with a curly apostrophe ("We’ll send …") is still a promise (R63)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/docs-promise-apostrophe
- What changed: agent/booking_agent.py DOCS_PROMISE matches will/’ll/'ll send|forward|provide; R63 "We’ll send you the dangerous goods documents shortly" went to a person.
- How verified: agent 1267 passed (R63, R40 and R39 wordings)
