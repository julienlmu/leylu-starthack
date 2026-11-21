# main = what Orhun deploys: his resolution of main + #116 (dce366c)
- Who: Julien (tool: Claude Code)
- Branch: julien/align-live
- What changed: Orhun and I merged main and #116 at the same time, in opposite directions (#121 took #116's exclusions; Orhun's dce366c keeps #116's booking rules AND main's #112 follow-ups, with main's exclusions module and pricing filter). main now carries exactly his choice: agent/ and backend/ are identical to dce366c (diff empty), so live and main agree and #120 (customer constraints, built on main's #115 exclusions) merges onto it
- Files touched: agent/{booking_agent,exclusions,humanizer,rfq_agent}.py, agent/test_{booking_tracking,exclusions}.py, agent/.gitignore, backend/{pricing,test_pricing}.py (all = dce366c)
- Contract/API changes: none
- New env vars / packages: none
- How verified: make check green (agent 405 + 15 xfailed, backend 75); eval replay 25/25 ($0); airline lists, stray negations and round 42 still correct with main's exclusions
- Known issues / TODO: none
- Heads-up for teammates: the exclusions file is main's: agent/.exclusions.json (not excluded_airlines.json)
