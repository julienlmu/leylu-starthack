# Portal booking down ("Contact the airline directly") books by email (R45)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/portal-down-email
- What changed: backend/booking.py: a 503 whose text says to contact the airline is surely not booked, so the error carries "book it by email with the airline" and the agent's email booking (#83) asks the airline; any other 5xx stays a person check (no double booking).
- How verified: backend 76, agent passed (new: 503 contact-the-airline → 502 with the email phrase)
- 20:33: the mailbox answers 429 "one poll per 5 seconds": agent/main.py polls every POLL_SECONDS (default 5.2) and waits Retry-After on a 429.
- Airline email-booking: waiting for the confirmation no longer flags Needs a person (EMAIL_WAIT_QUIET); the confirmation mail no longer crashes on the missing reference (R46 KeyError).
