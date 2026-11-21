# Agent: thank-you mails after the booking no longer need a person
- Who: Orhun (tool: Claude Code)
- Branch: orhun/agent-booked-thanks
- What changed: a customer mail on a booked session without a question ("Thank you for booking, let me know once the airline confirms", "Thank you for confirming") is logged and left alone instead of "needs a person"; a question still goes to a person. Live rounds 2 and 3 each raised two such false alarms
- Files touched: agent/booking_agent.py, agent/test_booking_tracking.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: cd agent && uv run pytest -q → 66 passed (new test: thanks → no hand-over, question → hand-over)
- Known issues / TODO: none
- Heads-up for teammates: Julien, small change in booking_agent.py, please review
