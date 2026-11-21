# Bid booked as a portal rate (#102, merged unreviewed): never a second booking after an unclear portal answer
- Who: Julien (tool: Claude Code)
- Branch: julien/bid-book-safe
- What changed: #102 books a carrier-bid winner as a fresh portal rate of the same airline and falls back to the bid's own rate ID when that fails. It fell back on ANY non-200/201 answer, also on a 5xx where the portal may already have booked the fresh rate → two public bookings that can't be cancelled. Now it falls back only on a definite refusal (404/409/410); an unclear answer is a 502 for a person, and the next try books the same pending fresh rate (the portal answers 200 to a repeat)
- Files touched: backend/booking.py, backend/test_booking.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: make check green; the new test (fresh rate answers 503 → bid rate never booked, pending kept) fails without the fix
- Known issues / TODO: #102's theory (bid rate IDs give booked=false) rests on two rounds; watch the next bid-won bookings
- Heads-up for teammates: Orhun, booking changes please through a review first: bookings are public and can't be cancelled
