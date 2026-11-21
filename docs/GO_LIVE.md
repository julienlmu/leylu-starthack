# GO_LIVE.md: stop missing RFQs (for Orhun, who runs the live Mac)

> Written Sat 21 Nov ~16:15 Berlin, after the first two scored rounds. Orhun implements everything here; Julien please review the `agent/` parts.
> Rule behind every item: **no answer = 0 points.** A late answer still scores: a quote at 3:00 can earn accuracy 45 + cost 40 + roughly 11 of 15 time points (if time points drop linearly from 2 to 6 min).

## Where we stand (public board, 16:10)
| | |
|---|---|
| Rounds sent | 2 (16:00:59 and 16:07:05 Berlin, then about every 6 min) |
| Leylü | rank 7/14, 49.14 pts, answered 2, **accepted 1**, 1 booking (FRA-JFK, Solace: quote → accept → book works) |
| Leader | makeanothermd 120 pts, 2/2 accepted |

Only one of our two answers is accepted (round 2 was still open at 16:10, so the other is rejected or pending). Step 1.5 shows which and why. The no-answer paths below are what to fix either way.

## Why requests get no (good) answer
The agent sends **nothing** when it can't price a request; it only marks the session "needs a person" in the UI, and nobody is told.

| Path (agent/rfq_agent.py) | When | On the live Mac today |
|---|---|---|
| `to_rfq` reports missing fields → `hand_over` | e.g. door-to-port with no airport named: RFQ #269 Bergisch Gladbach → ORD, "missing: origin" | fixed on main (#33), **not deployed** |
| `/api/price` returns `chosen: null` → `hand_over` | door-to-port and no trucker bid by the 90 s cut-off (`backend/pricing.py`: "door-to-port but no trucker bid") | **every door-to-port RFQ**, because `CARRIERS_FILE=no-carriers.json` sends no bid requests at all |
| same | lanes priced only by airline bids (ASU, KTM, PPT, TNR, ULN) | **every such RFQ**, same reason |
| exception → stage `failed` | any crash in the RFQ thread | — |

## 1. Do now on the live Mac (~5 min)
1. Pick the moment: right after `logs/agent.log` shows `Quote sent` for the current round. Never restart while an RFQ is in its bid round: that RFQ is lost (its mail id is already past `.since_id`).
2. Deploy main. `orhun/deploy-live` is an ancestor of `main`, so this is a plain fast-forward with no conflicts:
   ```bash
   git fetch origin && git merge --ff-only origin/main
   ```
   It brings #31 (kit carrier list: 29 airlines by destination, 22 truckers by pickup zone), #33 (door-to-port origin from the pickup postcode) and Batu's live-stream fix.
3. Switch bids back on: delete the `CARRIERS_FILE=no-carriers.json` line from the Mac's `.env` (or unset it in the shell that runs `make live`). The default is now the kit list.
4. Restart: `kill $(cat logs/live.lock/pid)`, then `make live`. Check `curl -s localhost:8000/health` → `{"ok":true}`.
5. See why the rejected request failed (verdict + reason code per round):
   ```bash
   set -a; source .env; set +a
   curl -s -H "X-API-Key: $FIVEU_API_KEY" https://api.start-hack.5u.ai/v1/board/me | python3 -m json.tool | head -80
   ```
6. On the next RFQ, `logs/agent.log` must show `Asked N: …` (airlines, plus truckers for door-to-port), then `bid` lines, then `Quote sent`. Update the Carriers and Code rows in `docs/LIVE_STATUS.md`.

## 2. Code changes, in this order
**2.1 Door-to-port: wait for a trucker instead of giving up** (`agent/rfq_agent.py`, `_carrier_round`)
Today the loop stops at `sent_at(mail) + cutoff_s` (90 s) and late trucker bids are dropped, so a door-to-port RFQ without a trucker answer by 90 s gets no quote. Change: while the RFQ has a `pickup` and no usable bid with `leg == "pickup"` has arrived, keep waiting past the cut-off, up to `sent_at(mail) + PICKUP_DEADLINE_S` (new env, default 270 s); stop as soon as the first usable trucker bid is in. Air bids keep the 90 s cut-off. Test: a fake trucker reply at 120 s still produces a quote.
Why: at 4:30 we still get up to ~90 of 100 points; handing over gets 0.

**2.2 Tell a human instantly** (`backend/app.py`, `add_event`, line ~127)
When an event with kind `needs_human` or `error` is stored, POST its text to `https://ntfy.sh/$NTFY_TOPIC` (new env, skip when unset) as a FastAPI background task, so the request never waits on the push. Everyone installs the ntfy app and subscribes to the topic; pick a hard-to-guess topic name (anyone who knows it can read it). Then a person can rescue the request inside the 6-minute window: Sessions UI → session → intervene → send.

**2.3 Last resort at ~5:00: team decision first**
If there is still no all-in price at ~5:00, today we send nothing (0 points for sure). Option: quote the best air price plus an estimated pickup (from earlier trucker bids in the same zone, once we have some). Ask 5U first whether a quote *below* the best price can be accepted; decide together, don't build it before that.

**2.4 Board watcher** (Ulas, PR #32, read-only)
Polls the board every 30 s and pushes rejected / no-answer verdicts and new reason codes to the phone. It only reads, so it can run on any machine (not the agent's). Nothing for Orhun to do unless you want it on the Mac too.

## 3. Rules while live (unchanged)
- Only the Mac runs the agent; test with `make agent-mock`. Every gateway call on the team key counts in that hour's cost score, so no live-key testing.
- Restart only between rounds (step 1.1).
