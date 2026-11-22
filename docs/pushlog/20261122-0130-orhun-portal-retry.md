# portal-retry: a portal 503 is retried until T+4:00; the sheet price only as the last resort (R93 too_low)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/portal-retry
- What changed:
  - R93 / session 95: 5U's rate portal answered 503. All 13 teams quoted from the sheet and were rejected too_low; ours was EUR 488.30. 5U's reference was the portal price.
  - New PORTAL_RETRY (default on). The rate desk is still asked first. If the desk gives no rate, /api/price is called again while the why line says the portal failed (503/502/504/429). The pause grows from 10 s by ×1.5, at most 25 s, to stay inside the team's 10 rate calls per minute.
  - The first answer without a portal failure is quoted. At PORTAL_RETRY_LAST_SECONDS (240 s after the RFQ) the sheet/bid price goes out as the last resort, with a session note.
- Files touched: agent/rfq_agent.py, agent/test_portal_retry.py (new), agent/test_next_traps_15b.py (its rate desk tests turn the retry off), agent/AGENTS.md
- Contract/API changes: none
- New env vars / packages: PORTAL_RETRY (on), PORTAL_RETRY_LAST_SECONDS (240)
- How verified: agent 2472 passed / 13 xfailed, backend 243 passed. The test where the portal answers on the 3rd retry quotes 612.40, not the sheet's 488.30. The test where it stays down sends the sheet price at the deadline.
- Known issues / TODO: an RFQ during an outage now quotes as late as T+4:00 (speed points lost; too_low scores 0 anyway).
- Heads-up for teammates: none

## Second push: a person can feed the portal's web form rate back
- The portal also moved to a web form with a "solve the sum" check (start-hack.5u.ai/portal/ui). We don't automate that form.
- When the API fails, the session gets a needs_human event (ntfy) with the exact form inputs (origin, destination, weight kg, cbm, chargeable kg, airline codes) and the command to feed a rate back.
- New `agent/portal_rate.py <session> <airline> <EUR total> [days] [rate ID]` stores it as a bid with `manual_portal: true`. The retry loop picks it up, prices again with it and quotes 20 s after the first typed rate (time for a second airline). needs_human is cleared when the loop ends.
- Tests: test_portal_retry.py (+2).
