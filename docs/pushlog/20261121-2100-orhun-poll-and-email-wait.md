# Mailbox 5 s poll, quiet airline email-booking wait, confirmation fix (live since 20:37-20:42)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/portal-down-email → orhun/deploy-next2
- What changed:
  - agent/main.py: POLL_SECONDS (default 5.2) and Retry-After on a 429: 5U allows one mailbox poll per 5 s since ~20:33
  - agent/booking_agent.py: EMAIL_WAIT_QUIET: an email booking waiting for the airline's confirmation is not Needs a person; handle_booking_confirmed builds the customer mail from the updated booking (R46 KeyError 'booking_reference', rescued by the retry)
- How verified: agent 405, backend 76 at the time; R46/R47 email bookings confirmed automatically
