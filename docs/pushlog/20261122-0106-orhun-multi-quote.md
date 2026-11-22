**Task:** R89/R90 multi-shipment by hand, R88 -20 · **Agent:** Claude Code

# Multi-shipment quotes, "book only the first", and a 25 s booking grace (MULTI_QUOTE, BOOK_GRACE_S)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/requote
- MULTI_QUOTE (default on), `shapes.py`:
  - Fixes "separate all-in price for each shipment rather than a combined total". ONE_TOTAL read "combined total" as a wish for one total, so a person had to answer (R89, R90). A separate-price wish now wins.
  - `shapes.all_lots` splits the lots (destination, pieces, kg, cbm, commodity per line).
  - `rfq_agent._multi_quote` prices the other lots with the trucker bids of the round, then writes one mail with a numbered block and one amount per shipment. A lot without a price is named as such.
  - The session quote is lot 1 with `quote.lots` (each lot's rfq + option). This is a minimal version: the hardening thread's fuller one can replace it.
- "Book only the first shipment for now, we'll confirm the second later": `booking_agent.lot_pick` picks the lot, by ordinal or by destination code. The session quote and rfq become that lot and it is booked. "Both" or unclear wording keeps the usual intent reading.
- BOOK_GRACE_S (default 25; 0 = book at once), for R88 (-20): the customer cancelled 19 s after their yes, and the booking was already requested. The yes now waits 25 s. A newer mail in the session that cancels or changes the figures wins, and nothing is booked. Before a booking, a cancellation gets "nothing booked, nothing to cancel" (one mail).
- Tests: test_night_traps.py (R90's mail split, MULTI_QUOTE off, lot pick, second thoughts); conftest sets BOOK_GRACE_S=0. Agent 2335 passed, backend 241.
- Dry-run on R90's real mail: RUH Tamarind EUR 2,059.28 and GRU Ibisair EUR 5,383.54, the same as the hand-sent quote.
- New env vars: MULTI_QUOTE (on), BOOK_GRACE_S (25).
