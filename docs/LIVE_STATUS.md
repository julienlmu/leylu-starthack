# LIVE_STATUS: where the live forwarder runs

**The live agent runs ONLY on Orhun's MacBook, since Sat 21 Nov 15:40 Berlin** (last restart 16:17).
Nobody else starts `make live` or `make agent` against the 5U mailbox: two workers answer every mail twice.
Need to test? Use `make agent-mock` (fixtures, nothing is sent).

| | |
|---|---|
| Machine | Orhun's MacBook (on power, lid open, kept awake by `caffeinate`) |
| Started with | `scripts/live.sh` (= `make live`): backend :8000, agent on the live 5U mailbox, Sessions UI :3000, each restarted on crash |
| Code | branch `orhun/deploy-live` = `main` + PR #36 (overnight safety fixes) + PR #37 (no person for thank-you mails after booking) |
| Model | `gpt-6-luna` with `reasoning_effort: none` (PR #23) |
| Carriers | on since 16:04: the start-kit list (29 airlines by destination, 22 truckers by pickup zone, #31); door-to-port origin from the pickup postcode (#33). Trucker bids are chosen 50/50 on price and days (`PICKUP_CHOICE=balanced` in the Mac's `.env`) |

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

## Results so far
Round 1 (16:01) no automatic answer (origin missing, fixed by #33), round 2 and 3 accepted and booked. Live verdicts: `/v1/board/me`.
