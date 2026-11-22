# flaky-desk-test: the rate-desk tests no longer flake under load
- Who: Julien (tool: Claude Code)
- Branch: julien/flaky-desk-test
- What changed: test harness only (agent/test_next_traps_15b.py `_run`): the desk wait 2 → 3 s, the wait for the desk mail 4 → 8 s, the worker join 8 → 20 s; the silent-desk time bound 6 → 8 s. `test_portal_down_asks_the_rate_desk_once_and_quotes_its_rate` failed ~1 run in 4 when several make checks shared the CPU (reviewers noted it on #263/#264/#266).
- Files touched: agent/test_next_traps_15b.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: 3 parallel runs of the file + 1 solo: 143 passed each; make check green
- Known issues / TODO: none
- Heads-up for teammates: none
