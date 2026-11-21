# #102 review: a portal server error on the fresh rate never books the bid too
- Who: Orhun (tool: Claude Code)
- Branch: orhun/bid-book-guard
- What changed:
  - backend/booking.py: after the fresh portal rate's booking answers anything but 400/404/409/410/422 (e.g. a 5xx that may have booked), the bid's own rate ID is not booked; the session gets a booking error for a person (and the agent's email-booking path), so no double booking
- Files touched: backend/booking.py, backend/test_booking.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: backend 72 passed (new: fresh rate answers 503 → 502, bid rate never booked), agent passed
- Heads-up for teammates: reviewer note on #102
