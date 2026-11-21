# Docs: fix list for Orhun (live machine, backend, ops)
- Who: Julien (tool: Claude Code)
- Branch: julien/orhun-fixes-doc
- What changed: docs/ORHUN_FIXES.md lists what is still open from the reviews of #14–#21, #30 and the first live round, by priority (P0 now on the live Mac, P1 before the night, P2 cleanup), each with file:line, the failure seen and the fix
- Files touched: docs/ORHUN_FIXES.md
- Contract/API changes: none
- New env vars / packages: none
- How verified: docs only; `make check` green
- Known issues / TODO: none
- Heads-up for teammates: Orhun, P0 first: merge main into orhun/deploy-live, remove CARRIERS_FILE=no-carriers.json, restart
