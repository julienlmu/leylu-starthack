# A manual reply becomes the quote, so the customer's "yes" is booked (round 7 lost its booking and tracking bonus)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/manual-quote
- What changed: POST /api/sessions/{id}/intervene send, on a session without a quote, prices its rfq and stores the chosen option as the quote (stage quoted, quote.manual = true); if the agent had handed the session over (needs_human), the session is unpaused so the agent handles the customer's answer (accept → book by rate ID → booking mail). Round 7: Deniz accepted the hand-written quote, the agent answered "no open quote", no booking, no +10 (SCORE_ANALYSIS §3.4)
- Files touched: backend/app.py, backend/test_overnight.py
- Contract/API changes: intervene send may set stage/quote and unpause a handed-over session
- New env vars / packages: none
- How verified: backend 63 passed (new: handed-over RFQ + manual reply → quoted with the priced option, unpaused)
- Known issues / TODO: the stored option is our pricing's choice, not parsed from the person's text
