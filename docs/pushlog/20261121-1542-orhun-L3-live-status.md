# L3: docs/LIVE_STATUS.md, where the live agent runs
- Who: Orhun (tool: Claude Code)
- Branch: orhun/live-status
- What changed: docs/LIVE_STATUS.md: the live agent runs only on Orhun's Mac since 15:40 Berlin, from orhun/deploy-live, gpt-6-luna, no bid requests for now; why not the AMD box; how to check logs
- Files touched: docs/LIVE_STATUS.md
- Contract/API changes: none
- New env vars / packages: none
- How verified: docs only; on the Mac /health answers {"ok":true} and the agent log shows "worker running (live 5U mailbox)"
- Known issues / TODO: none
- Heads-up for teammates: do not start a second live agent anywhere
