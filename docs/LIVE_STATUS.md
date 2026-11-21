# LIVE_STATUS: where the live forwarder runs

**The live agent runs ONLY on Orhun's MacBook, since Sat 21 Nov 15:40 Berlin.**
Nobody else starts `make live` or `make agent` against the 5U mailbox: two workers answer every mail twice.
Need to test? Use `make agent-mock` (fixtures, nothing is sent).

| | |
|---|---|
| Machine | Orhun's MacBook (on power, lid open, kept awake by `caffeinate`) |
| Started with | `scripts/live.sh` (= `make live`): backend :8000, agent on the live 5U mailbox, Sessions UI :3000, each restarted on crash |
| Code | branch `orhun/deploy-live` = `main` + Orhun's open PRs #16 #17 #18 #21 (pricing, booking, runner, tariff ingestion) |
| Model | `gpt-6-luna` with `reasoning_effort: none` (PR #23) |
| Carriers | `CARRIERS_FILE=no-carriers.json` for now: no bid requests, quotes come from the rate sheets + portal right away. Door-to-port RFQs go to a person (no trucker bid). Remove the line once `agent/` has the real kit carrier list |

## Why not the AMD cloud box
Its outbound traffic goes through a proxy that answers `403` for `api.start-hack.5u.ai` (no direct internet either), so the agent can't reach the mailbox, portal or gateway there.

## Checking on it (on Orhun's Mac, repo root)
- `tail -f logs/agent.log`: every mail, route, quote
- `tail -f logs/backend.log`: API calls, portal errors
- `curl -s localhost:8000/health` → `{"ok":true}`
- Sessions UI: http://localhost:3000
- Restart: `kill $(cat logs/live.lock/pid)`, then `make live` again

## Changing what runs
Merge into `main`, then Orhun (or his Claude) merges `main` into `orhun/deploy-live` on the Mac and restarts the runner. Don't switch branches in that checkout while it runs. Update this file when the machine, branch or model changes.
