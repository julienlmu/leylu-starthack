# ui-command-cancelled: a cancelled booking shows "Cancelled", not "Booked" (saved design, not live)
- Who: Julien (tool: Claude Code)
- Branch: julien/ui-command + design/command-ui-v1 (draft PR #279, do not merge)
- What changed: from the end-to-end test against a local backend: the status badge on Requests and in the drawer showed a green "Booked" for a cancelled booking (badge() never checked booking.status); it now shows a red "Cancelled". The Bookings count in the sidebar no longer counts cancelled bookings.
- Files touched: frontend/lib/command/derive.ts, frontend/components/command/shell.tsx
- Contract/API changes: none
- New env vars / packages: none
- How verified: eslint (command folders) + tsc clean
- Known issues / TODO: none
- Heads-up for teammates: design only, not live
