# EMERGENCY_FIXES.md: live incidents and their fixes (for Orhun, who runs the live Mac)

> Kept up to date by Ulas from the board watcher (ntfy topic `leylu-watch-31`, buzzes within ~15 s) and an hourly check after each hour's setup change.
> Newest incident first. Each one: what the board showed, the likely cause in our code, the fix, and whether it needs a restart.
> **Restart only between rounds**, right after `logs/agent.log` shows `Quote sent` (a restart mid-round loses that RFQ).

## How alerts reach you
1. The watcher (Ulas's laptop, public board every 15 s) pushes to ntfy `leylu-watch-31`: no answer at 1:30, answered but NOT accepted, round closed without answer, can't reach 5U.
2. **Orhun's Claude subscribes to the same topic and fixes on the Mac:** see `docs/EMERGENCY_PLAYBOOK.md` (one paste-in prompt, a Monitor command, what to do per alert).
3. Within ~1 min Ulas also pushes a diagnosis line to the topic and adds the incident here.
4. In-round rescue is only possible on the Mac: Sessions UI → the session → intervene → send.

## Incidents

### #3 · 16:55 · round 1 was rejected as `too_low`: quoting under the best price is rejected too
- **Board (`/v1/board/me`):** round 1 verdict `rejected`, reason `too_low`, answered at 16:06:13 (5:14 after the RFQ, the hand-sent reply after the agent handed #269 over).
- **Cause:** the door-to-port price without the trucker pickup leg (most likely) came out more than 5% under the best all-in price.
- **Rule for everyone:** a hand-sent quote for door-to-port must include the pickup. **Don't build** the "last resort: quote the air price" idea (GO_LIVE 2.3 / BONUS_PLAN): it would be rejected as `too_low` as well.

### #2 · 16:55 · rounds 5, 6, 7 accepted but `booked: false`: no tracking +10 there
- **Board (`/v1/board/me`):** rounds 5, 6 and 7 are `accepted` with `booked: false`; rounds 2, 3, 4, 8, 9 are `booked: true`. Our bookings list has confirmed bookings for round 5 (STR-EZE Fjordline BK-ZCW3WSXE, 1227.96 kg) and round 6 (DUS-KUL Fjordline BK-5QTMB4NR, 1548.96 kg), and **none for round 7**.
- **Why it matters:** the tracking bonus is "+10 on a booked shipment"; if 5U doesn't count these bookings, rounds 5-7 earn no tracking points (up to -30, and more every round it repeats).
- **Check (Mac):** the booking events of the round 5, 6 and 7 sessions. Did we book the quoted rate ID or a fresh one (`booking.py`: "booked a fresh rate …")? Did the quote come from a carrier bid or a sheet (no `R-` rate ID, so `/api/book` can't book it)? For round 7: did the customer accept, and did `/api/book` fail?
- **Likely fix:** book exactly the quoted offer: the quoted portal rate ID, or, for a bid or sheet option, the way 5U expects (ask in #5u-ai if unclear). See BONUS_PLAN.md step 1.

### #1 · 16:39 · round 7 answered late (~2:10-2:24), accepted, -1.2 time points
- **Board:** alert "no answer from us after 1:39" (9 teams had answered), then "answered at 2:24 after all". Accepted with +58.83 instead of +60 (time points start dropping at 2:00).
- **Likely cause:** `agent/rfq_agent.py` `_carrier_round` stops waiting only when **every** asked carrier has replied, or at `BID_CUTOFF_SECONDS` (90). We ask every airline that serves the destination (up to 15, PR #31), but the brief says only 2-5 per destination answer, so on most lanes the loop always runs the full 90 s, then prices and sends: the quote lands after 2:00.
- **Check first (Sessions UI, round 7's session):** event times of `carrier_asked` → `bid` lines → "Cut-off: x of y answered" → `priced` → `quote_sent`. If the cut-off line says e.g. "3 of 12 answered" at 90 s and `quote_sent` follows 30-50 s later, this is it.
- **Fix A, now, no code:** none safe. Lowering `BID_CUTOFF_SECONDS` drops slow bids, and a missed winning bid costs up to 60 points, far more than the ~1-2 time points. Keep 90 until B.
- **Fix B, code (agent/rfq_agent.py, `_carrier_round`):** stop when no new bid has arrived for `BID_QUIET_SECONDS` (new env, default 15) after at least one usable air bid (and, for door-to-port, one trucker bid); keep the 90 s cap. The answering carriers are automated agents, so their bids should come close together. Test: 3 bids at 10/12/20 s, then silence → quote at ~35 s, not 90 s.
- **Also worth a look:** the 30-50 s between the cut-off and `quote_sent` (if the timeline shows it): `/api/price` should be fast because the portal is asked when the RFQ is PATCHed.
- **Restart:** only for B, between rounds.

## Hourly change check (from 17:00)
After each hour starts, Ulas checks the last rounds on the board (`python watch/board_watch.py --report`), the watcher log, new PRs and `LIVE_STATUS.md`, and adds an incident here when something changed. Likely change types: new or changed tariffs by mail, portal lanes/airlines, rate limit, rate-ID lifetime, mail formats, new languages.
