**Task:** all of main live, without losing CANCEL_AUTO · **Agent:** Claude Code

# main dc96da3 into the live branch (fb8ab46), CANCEL_AUTO and the night fixes kept
- Who: Orhun (tool: Claude Code)
- Branch: orhun/requote
- Merges main through dc96da3: #234/#236 (insurance "worth"), #238 (between style, the QUOTE_STYLE default), #239 (desk wait), #235/#240 (portal retry), #241 (desk visibility).
- Conflicts resolved to main's side: insurance.py (main's "worth" with the amount-only guard), the portal-retry needs_human flag (main only clears its own flag), test_portal_retry.py and test_next_traps_15b.py.
- Kept from the live branch: CANCEL_AUTO, BOOK_GRACE_S, REQUOTE, MULTI_QUOTE/lot_pick/RESEND, DEADLINE_AIR, MAIL_HUMAN.
- New test `test_night_traps::test_r88_no_cancellation_mail_loop`: three "let me know once the airline confirms the cancellation" mails get no reply (main alone loops, per Batu's backtest).
- Tests: agent 2534 passed, backend 245. QUOTE_STYLE stays unset in .env and PICKUP_CHOICE=balanced.
