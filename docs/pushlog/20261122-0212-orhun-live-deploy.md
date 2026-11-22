**Task:** one deploy branch: live + main · **Agent:** Claude Code

# orhun/live-deploy = orhun/requote + main e1dec06 (#251 CANCEL_AUTO with portal cancel, #252 pickup line, #253)
- Who: Orhun (tool: Claude Code)
- Conflicts in booking_agent.py resolved: main's cancel rules (past-tense CANCELLED, CANCEL_ASK, _no_auto_cancel, CANCEL_PORTAL + _cancel_on_portal) are the one cancel path. Kept from the live branch: BOOK_GRACE_S, lot_pick, RESEND/lots_status_text.
- #250 portal_web stays off (PORTAL_WEB defaults to off).
- Tests: agent 2566 passed (incl. test_night_traps r88 no-loop), backend 268.
- .env for this deploy: PICKUP_REUSE_TOLERANCE=0.5 (#252).
