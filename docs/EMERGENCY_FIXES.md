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

### AUTO · 01:34 · round 95 rejected `too_low`
- Board: we answered at 2:15; 0/12 teams accepted.
- RFQ (round sent 00:31:50 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 01:28 · round 94 rejected `too_low`
- Board: we answered at 2:20; 0/10 teams accepted.
- RFQ (round sent 00:25:44 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 01:22 · round 93 rejected `too_low`
- Board: we answered at 2:15; 0/13 teams accepted.
- RFQ (round sent 00:19:41 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 01:14 · round 92 rejected `too_low`
- Board: we answered at 0:43; 1/3 teams accepted.
- RFQ (round sent 00:13:37 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 01:08 · round 91 rejected `too_low`
- Board: we answered at 0:39; 0/7 teams accepted.
- RFQ (round sent 00:07:32 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 00:43 · round 86 no answer `-`
- Board: we answered at never; 7/7 teams accepted; field booked Polaris Air Logistics (7 teams).
- RFQ (round sent 23:37:10 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 00:32 · round 85 rejected `too_high`
- Board: we answered at 0:38; 7/9 teams accepted.
- RFQ (round sent 23:31:03 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 23:43 · round 77 rejected `no_pdf_offer`
- Board: we answered at 0:46; 3/10 teams accepted.
- RFQ (round sent 22:42:31 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 23:37 · round 76 rejected `no_pdf_offer`
- Board: we answered at 0:42; 0/9 teams accepted.
- RFQ (round sent 22:36:28 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 23:13 · round 72 rejected `wrong_language`
- Board: we answered at 0:45; 4/10 teams accepted; field booked Xenon Cargo Airlines (1 teams).
- RFQ (round sent 22:12:11 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 22:59 · round 69 no answer `-`
- Board: we answered at never; 5/8 teams accepted; field booked Fjordline Air Cargo (4 teams).
- RFQ (round sent 21:53:55 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 22:49 · round 68 rejected `too_high`
- Board: we answered at 0:52; 5/9 teams accepted; field booked Polaris Air Logistics (2 teams).
- RFQ (round sent 21:47:48 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 22:42 · round 67 rejected `too_low`
- Board: we answered at 0:51; 5/7 teams accepted.
- RFQ (round sent 21:41:43 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 22:36 · round 66 rejected `too_low`
- Board: we answered at 0:58; 6/7 teams accepted; field booked Gannet Airways (1 teams).
- RFQ (round sent 21:35:39 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### AUTO · 22:35 · round 65 no answer `-`
- Board: we answered at never; 7/8 teams accepted; field booked Xenon Cargo Airlines (7 teams).
- RFQ (round sent 21:29:33 UTC): mailbox not read (5U allows one poll per 5 s; the agent needs them)
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### #11 · 21:15 · spam mails now arrive: ignore them (no reply, no LLM call)
- **5U (to Ulas):** the mailbox can now receive spam. It must be ignored: no quote, no reply.
- **Risk today:** `agent/router.py` treats an unknown sender's mail as a customer RFQ, so a spam mail can (a) cost an extraction LLM call (the cost score is gateway spend per accepted quote, so spam spend lowers it), (b) get a reply or a hand-over mail, (c) create a session that clutters the UI and the "needs a person" queue.
- **Fix (for Orhun's Claude):**
  1. `agent/router.py`: a rules-first `is_spam(mail)` **before** any extraction, free:
     - no shipping facts at all: no airport code/city + no weight/volume/pieces + no "quote/rate/price/freight/shipment" words;
     - marketing / phishing / scam words: unsubscribe, newsletter, "click here", "limited offer", lottery/winner, crypto/bitcoin, SEO, "verify your account", password, "update your bank details", invoice/payment links;
     - mostly links, or an attachment with an executable/archive type;
     - automatic replies: "out of office", "automatic reply", "delivery status notification", mailer-daemon.
     A mail that also contains real shipping facts is NOT spam (an RFQ can mention "unsubscribe" in its footer).
  2. Spam → log it as one `routed` event ("spam, ignored"), no session stage change, **no reply, no LLM call, no hand-over**.
  3. Carrier-side: an out-of-office or spam reply to our bid request must not count as a carrier answer (don't end the bid wait for it, don't parse it as a bid).
  4. Tests + `agent/evals/traps.json` cases: newsletter, phishing ("update your bank details"), lottery, out-of-office, and an RFQ with an "unsubscribe" footer that must still be quoted.
- **Restart:** between rounds.

### #10 · 21:05 · rounds 48, 49: `adjustment: -22.5` = booked at a changed price without asking the customer (URGENT, every booking)
- **Board (`/v1/board/me`):** rounds 48 and 49 accepted, accuracy 45, time 15, booked, tracking 10, but a new point line **`adjustment: -22.5`** each.
- **5U (in person, to Ulas):** between the customer's acceptance and our booking the price can still change. Booking at a different price than the customer accepted is penalised. If the price changed, **ask the customer again before booking**.
- **Where we do it today:** `backend/booking.py` books a fresh portal rate when the quoted rate ID expired (410) or was taken (409), and only blocks it when the fresh air price is more than +5% above the quote. Smaller changes, or any change on the pickup leg, are booked silently: that is the penalty.
- **Fix (for Orhun's Claude):**
  1. `backend/booking.py`: before every booking, compare the **all-in total we would book now** (fresh rate + pickup leg, same currency) with the total the customer accepted (`session.quote.total`). Equal (allow rounding, |diff| < 0.01 EUR): book as today. Different (up or down): **don't book**; return `{"status": "price_changed", "old_total", "new_total", "rate_id", "valid_until"}` and store it on the session (`booking.pending`).
  2. `agent/booking_agent.py`: on `price_changed`, reply in the customer's thread: the price changed, the new all-in total, "shall we book it at this price?" (mention only the new amount; templates in all languages, humanizer style). Set stage `awaiting_reconfirm`. Mark the session so a plain "yes" in the thread now books the **new** offer.
  3. On the customer's yes: book the stored rate ID if still valid; if it expired again and the price moved again, repeat step 2; if unchanged, book. On "no": outcome lost, no booking.
  4. Never re-price silently between the yes and the booking (no fresh-rate swap without consent).
  5. Tests (`backend/test_*`, `agent/test_booking_tracking.py`, add a trap case): unchanged price → booked; 410 with a different fresh total → no booking + reconfirm mail; customer yes → books the new rate ID; customer no → nothing booked.
- **Watcher:** now pushes any round with an `adjustment` the moment 5U shows it.
- **Restart:** between rounds, ASAP (every booking with a price change costs 22.5).

### #9 · 20:55 · 5U now allows ONE mailbox poll per 5 seconds per team key (hourly change?)
- **Evidence:** `GET /v1/mailbox/messages` answers `429 Too Many Requests`, `{"detail": "one poll per 5 seconds", "retry_after": 1}`, since ~20:45. The live agent polls every 1.5 s, so about 2 of 3 polls now fail (it survives them, but every failed poll is wasted and any other reader steals its slot).
- **Fix (for Orhun's Claude):**
  1. `agent/main.py` / `agent/inbox.py`: poll every 5 s, not 1.5 s (or honour `retry_after` on a 429 instead of hammering). One poll per 5 s still picks up each RFQ within 5 s.
  2. Nothing else may poll the mailbox with the team key while the agent runs (no scripts, no Codex): each such poll can delay an RFQ or a carrier bid by 5 s. Ulas's watcher stopped reading the mailbox for this reason.
  3. Trap heads-ups (docs/POSSIBLE_TRAPS.md) therefore belong in the agent: it already has every mail; have `agent/gate.py` push its holds/findings to ntfy topic `leylu-watch-31` (it already flags holds) so the team sees them in-round.
- **Restart:** between rounds.

### #8 · 20:15 · round 42 rejected `excluded_airline`: the customer banned an airline, we ignored it (URGENT, new trap, will repeat)
- **Board:** round 42 (sent 20:09:57, Wiesbaden 65797 → ULN, door-to-port, 8 pcs, 911 kg, 3.27 cbm) `rejected`, reason `excluded_airline`; 0 of 11 teams accepted at the time.
- **The RFQ (mail 10824, meyer-industrie@):** "Please do not offer **Zephyr Steppe Cargo (ZS)** for this shipment **or for any of our future inquiries**."
- **Why it bites us:** ULN is bid-only (kit carrier list: Zephyr Steppe, Himalaya Bridge, Lagoon Isles, Pampero; no portal lane). Nothing in agent/ or backend/ reads exclusions, so the cheapest/balanced choice can be the banned airline.
- **Fix (for Orhun's Claude):**
  1. `agent/extract.py`: add `excluded_airlines` (names and/or codes) to the one extraction call (schema + prompt line: "airlines the customer says not to use"). Free fallback in code: regex `(?:do not|don't|never|not)\s+(?:offer|use|book)\s+([A-Z][\w ]+?)(?:\s*\(([A-Z0-9]{2})\))?` on the body.
  2. **Persist per customer** (the mail says "any of our future inquiries"): store exclusions by sender address in the CRM / a small JSON, and merge them into every later RFQ from that sender.
  3. Filter before choosing: drop excluded airlines from carrier bid requests (`carriers_for`) and from the options in `backend/pricing.py` (match name or code). If nothing is left, hand over rather than quote the banned airline.
  4. Add round 42 to `agent/evals/traps.json`; test that ZS is never quoted and that a later RFQ from meyer-industrie@ also skips ZS.
- **Restart:** between rounds.

### AUTO · 20:10 · round 42 rejected `excluded_airline`
- Board: we answered at 0:37; 0/6 teams accepted.
- RFQ (round sent 19:09:57 UTC): 'Air freight quote request to ULN' from meyer-industrie@hackloop.mail
- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the missing rule and a case in agent/evals/traps.json, test, deploy between rounds.

### #7 · 19:30 · 5U shows a "booking" point category that is always 0 for us (unknown points we may be missing)
- **Board (`/v1/board/me`):** every request's points now list `time`, `accuracy`, `cost`, `tracking` and **`booking`**. `booking` is 0.0 on every round, including fully booked ones (e.g. round 33: booked true, tracking 10, booking 0). The published rules list no booking points (45 / 15 / 40 + humanity 10 + tracking 10).
- **Also:** round 29 is `booked: false` too (tracking 0), on top of round 27 (#6): 6 rounds and 60 tracking points lost so far to bookings 5U doesn't count.
- **Cost is fine:** 39.73 of 40 per accepted quote.
- **To do:** ask 5U in #5u-ai what earns booking points (booking the exact quoted rate ID? booking within a time limit? the pickup leg?). The watcher now pushes the first time any round earns booking points, and when a round's cost drops below 39.

### #6 · 18:58 · round 27 accepted, booked, but 5U says `booked: false`: no tracking +10 (repeat of #2)
- **Board (`/v1/board/me`, now with points per request):** round 27 (sent 18:38:52) `accepted`, `booked: false`, points: time 15, accuracy 39.32, tracking **0**, total 54.32. Rounds 26 and 28 next to it: `booked: true`, tracking 10, total 70.
- **But we did book it:** BK-6PS4QHE2, HAM-EZE, booked 18:39:59 (the only booking in that round's window). Same pattern as rounds 5, 6, 7 (#2): a real booking that 5U doesn't count for the request.
- **Check (Mac):** round 27's session: did we book the quoted rate ID, or a fresh rate after a 410/409 (`backend/booking.py` "booked a fresh rate …")? Was the quoted option a carrier bid or sheet rate (no `R-` rate ID)? Compare with rounds 26/28, which counted. Likely rule: 5U only counts a booking of the exact quoted offer.
- **Also:** accuracy 39.32 instead of 45: we were ~0.6% above the best price.
- **Cost so far:** 10 tracking points per affected round (4 rounds = 40).

### #6 · 17:29 · round 15 rejected `too_high`; rounds 15/16 answered after 2:00
- **Evidence:** `/board/me`: R15 rejected `too_high` at 3:33; R16 accepted at 2:39 (watcher said 2:48). RFQ 3631: 11 pcs, 572 kg, 2.29 cbm to SGN, no attachment. We quoted Polaris MUC–SGN at EUR 1,258.20; the field booked Polaris (4 teams); Polaris bid 3756 was EUR 1,058.20. Zone 93 truckers asked for a postcode; no usable pickup bid was found.
- **Cause:** stale AMS–HKG subject did not affect the sent quote; likely the EUR 200 pickup uplift, source to confirm. `backend/pricing.py` defaults pickup choice to `balanced`; `agent/gate.py::review` has no high-price check. Latency is `agent/rfq_agent.py::_carrier_round` waiting for every reply / the 90 s cap and up to 270 s for pickup; `agent/carriers.py::carriers_for` emails all eligible carriers. No round 15 trap exists in `agent/evals/traps.json`.
- **Fix (for Orhun's Claude):** on the Mac, find mail 3631's session and run `agent/postmortem.py <session> --mail 3631`; inspect the `priced` event to identify the pickup option behind the extra EUR 200.
- **Fix (for Orhun's Claude):** if the session confirms the balanced pickup choice, honor `ask=cheapest` with the cheapest valid pickup option; add the round 15 MUC–SGN RFQ and expected pickup behavior to `agent/evals/traps.json`.
- **Fix (for Orhun's Claude):** add `BID_QUIET_SECONDS=15` in `agent/rfq_agent.py` after at least one usable air bid and, for door-to-port, one pickup bid; keep 90/270 s caps. Persist airline responders by destination and truckers by pickup zone in a JSON file next to `.since_id` in `agent/carriers.py`; use the full list when no responders are known. Test bids at 10/12/20 s → quote by ~35 s, known responders, and unknown-key fallback.
- **Priority:** URGENT (will repeat).

### #5 · round 11 rejected `dg_docs_missing`: dangerous goods were in a PDF packing list
- **Board:** the watcher reported round 11 rejected with reason `dg_docs_missing`; the latest public board shows round 11 closed, 11 teams answered, and 4 accepted. The team-key `/v1/board/me` endpoint was unavailable from this client.
- **The RFQ (mail 2534, lindqvist-medtech@, Lueneburg 21663 → YYZ, door-to-port, 4 pcs, 855 kg, 3.74 cbm, "maintenance spray cans"):** body says "non-dangerous"; the attached `packing-spec_33955.pdf` says **`UN1950, Class 2.1, Aerosols, flammable`** (reported by the prior mailbox diagnosis in this incident).
- **Cause:** `agent/attachments.py` on `origin/main` reads spreadsheet/document/text formats but returns no text for PDFs, so it misses the packing-list declaration and quotes the shipment as non-DG.
- **Fix branch: `ulas/dg-pdf-round11` (pushed, not merged).** Reads text strings from plain or Flate-compressed PDF streams, with a regression test for the round 11 UN1950 line. Focused attachment tests: 6 passed.
- **Restart:** Orhun must merge/deploy this branch on the Mac, then restart only between rounds after `Quote sent` appears in `logs/agent.log`.

### #4 · 16:56 · round 10 rejected `dg_docs_missing`: dangerous goods hidden in the attached packing list (URGENT, will repeat)
- **Board:** round 10 (sent 16:55:39) `rejected`, reason `dg_docs_missing`, answered at 0:39. Only 1 of 7 teams got it accepted (TALOS, booked Juniper Cargo Lines).
- **The RFQ (mail 2261, weidner-spielwaren@, Bad Homburg 61391 → GRU, door-to-port, 3 pcs, 715 kg, 2.65 cbm):** the body says "general cargo, **non-dangerous**", but the attached `PL_53839.xlsx` says **`Dangerous goods: UN1133, Class 3, Adhesives`**.
- **Cause:** `agent/extract.py` only reads the mail body; attachments (packing lists) are never looked at, so `dangerous_goods` stayed false and the quote treated it as general cargo.
- **Fix (agent, no LLM needed):**
  1. In `rfq_agent.handle_rfq`, before pricing: download the RFQ's attachments (`box.attachment(...)`, already used for tariffs) and regex-scan their text for `UN\s?\d{4}`, `Class\s?[1-9]` and "dangerous goods" (xlsx: unzip and read `xl/sharedStrings.xml` + sheet cells; csv/txt: as text; pdf: skip or `pdfplumber` in backend). The attachment wins over the mail body. Set `rfq["dangerous_goods"] = True` and keep the UN number/class.
  2. If dangerous: the quote mail must address the DG paperwork. Add to `agent/templates.py` `quote_text` one line like "Your packing list shows UN1133 (Class 3), so this ships as dangerous goods: please send us the Shipper's Declaration for Dangerous Goods and the safety data sheet (MSDS) before pickup." (in the RFQ's language).
  3. Pricing: prefer airlines that accept DG and add a DG surcharge if the rate sheets have one (check the start-kit sheets for DG columns or notes).
- **Until it's fixed:** any RFQ with an attachment is a trap candidate; the watcher will buzz "answered but NOT accepted" with `dg_docs_missing`.
- **Restart:** after the fix, between rounds.

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
