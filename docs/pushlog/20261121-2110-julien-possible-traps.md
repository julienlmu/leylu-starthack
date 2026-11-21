# POSSIBLE_TRAPS.md: corrections against main + traps we found today (on top of Ulas's file)
- Who: Julien (tool: Claude Code)
- Branch: julien/possible-traps-additions (PR into ulas/possible-traps)
- What changed: new §9 in docs/POSSIBLE_TRAPS.md: corrections (round 15 was a guessed pickup, not Amsterdam; rows already done on main with PR numbers; booked:false is not the bid-rate theory), still-unguarded traps (⭐ "only airline X", images), the follow-up/booking traps of today and their guards, live-operations threats (⭐ public ntfy topic steering Orhun's Claude, two workers, restarts, test-run spend, Mac sleep, cheaper models, per-round humanity)
- Files touched: docs/POSSIBLE_TRAPS.md
- Contract/API changes: none
- New env vars / packages: none
- How verified: each "done" row checked against main 3ab8651 and the merged PRs
- Known issues / TODO: "only airline X" is the most likely unguarded trap
- Heads-up for teammates: Ulas, merge into your branch if you agree
