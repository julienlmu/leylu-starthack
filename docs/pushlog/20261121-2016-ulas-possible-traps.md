# POSSIBLE_TRAPS: list of likely next 5U traps with signals and guards
- Who: Ulas (tool: Claude Code)
- Branch: ulas/emergency-fixes
- What changed: docs/POSSIBLE_TRAPS.md (customer instructions, hidden cargo, routing, mail format, spam/prompt injection, pricing, booking/tracking, process)
- Files touched: docs/POSSIBLE_TRAPS.md, docs/pushlog/
- Contract/API changes: none
- New env vars / packages: none
- How verified: based on today's rejections (dg_docs_missing, excluded_airline, too_low, too_high, booked=false); docs only
- Known issues / TODO: none
- Heads-up for teammates: starred rows first, as cases in agent/evals/traps.json
