**Task:** postmortem data for R85–R91 · **Agent:** Claude Code

# Session export for the accuracy postmortem (R85, R87, R89, R90, R91)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/postmortem-r85-r91 (from main)
- What: `docs/postmortem/sessions_r85_r91.json` holds sessions 87–93 from the live CRM, each with its events (mails, bids, priced options, gate notes, quotes, bookings). Our session id = 5U round + 2.
- Scanned for keys/tokens/passwords: none found. The data holds only hackloop.mail addresses and 5U rate IDs.
- Note: sessions 91 and 92 (R89, R90, multi-shipment) were priced and sent by hand. Their rfq/quote were PATCHed to lot 1 afterwards, and the hand-priced options are not in their `priced` events.
