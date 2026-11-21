# Confirm-questions answered from our data; clean quote subject for forward chains (R60)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/confirm-question
- What changed:
  - agent/booking_agent.py: "could you (please) confirm that your offer covers …" / "please confirm" (no condition, no change words, quote stored) gets templates.confirm_text: pieces, gross kg, cbm, pickup address and date, route, carrier, the all-in amount, and "Shall I go ahead and book it once the DG documents are in?" (DG) / "Shall I go ahead and book it?"; checked before the hold rule, quote stays open. CONFIRM_ANSWERS=off.
  - agent/rfq_agent.py + inbox.py: a quote to a RE:/FW:/WG:/AW: chain subject goes out as "Your air freight quote: STR → BOM, 11 pcs, 1,674 kg" in the same thread (in_reply_to kept). CLEAN_SUBJECT=off.
- How verified: agent 1269 passed (R60 reply with hold + confirm → confirmation, no booking, no person; "confirm the price is valid until Friday" still a person; R60 subject → clean subject)
- Curly quotes and full-width forms are normalised (NFKC, ’‘“” → ASCII) in booking_agent before every intent rule (R61/R63: "don’t", "won’t", "We’ll").
