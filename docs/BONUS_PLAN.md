# BONUS_PLAN.md: bonus points, in the order to build them (for Orhun)

> Sat 21 Nov ~16:30 Berlin. Facts from the public board (`/v1/board`, recorded every 15 s since 16:15) and `main`. Orhun implements; Julien please review the `agent/` parts; Ulas checks the results on the board.

## What the bonuses are worth
| Bonus | Points | How often | Who decides |
|---|---|---|---|
| **Tracking**: correct answer to `tracking@` on a booked shipment | **+10** | **every booking** (we book almost every accepted round) | 5U's scorer, automatic |
| **Humanity**: the accepted email that reads most human | +10 | jury award (also final-jury criterion 4) | jury |

Tracking repeats with every booking, so it's worth far more over the night than humanity. **Tracking already works for us:** our total went 169.14 → 179.14 at ~16:25 with no new accepted quote, ~17 min after our 16:08 booking (the same delay as makeanothermd's and start-milan's +10s at 16:18 / 16:19). So **every extra booking is worth +10 about 17 minutes later.**

## 1. Book every accepted quote (do first: each booking = +10 tracking later)
Today we can only book portal rates (`backend/booking.py:21` requires an `R-…` rate ID). A winning **sheet** or **carrier-bid** option can't be booked, so that round earns no tracking bonus. With carrier bids on since 16:04, bid winners will happen more often.
- On acceptance: get a fresh portal rate for the same airline (if it's on the portal for the lane) and book that; otherwise book by email with the airline (the portal's 503 answer describes that path).
- Check: on the board our `bookings` equals our `accepted` (16:25: 3 = 3, all portal airlines so far).

## 2. Keep tracking answers from failing (cheap insurance)
1. **Look at one real question** (on the Mac): `grep -n -i tracking logs/agent.log | tail -20`, or the `tracking_answer` events in the Sessions UI. Note which reference 5U quotes (`BK-…`, our `S-<id>`, the customer's reference, or only route and weight).
2. **Our own reference isn't recognised.** We book with `team_reference = S-<session id>` (`backend/booking.py:20`). A question quoting it is missed twice: `agent/tracking_agent.py` `REFERENCES` needs 2+ characters before the dash (`S-17` doesn't match: add `\bS-\d+\b`), and `backend/crm.py` `find()` (line 83) doesn't look at it (resolve `S-<id>` to that session).
3. **Never answer "send me the BK- reference" when we can find the shipment another way.** That answer scores 0. Fallback when no reference matches: the newest booked session on the same route (and weight, if given).
4. **Check:** each booking gives +10 about 17 min later. Ulas's board watcher prints `Points posted outside a quote: +10.00`; a booking without its +10 after ~25 min means a failed answer.

## 3. Humanity +10 (after 1 and 2)
Already live: hand-written quote, booking and tracking mails in 8 languages, one all-in amount, signed by a person (U4).
- Next: the one extraction call also returns the contact's **first name** and **formality** (du/Sie, tu/vous); the templates greet by name (`Hallo Herr Weber,` / `Hi Anna,`). A few extra tokens, no extra call. `agent/extract.py` (schema) + `agent/templates.py` (Ulas can do the wording).
- Don't let the LLM write the mail: numbers stay from code, and a second call would cost cost points.

## Not a bonus, but bigger: cost points post at ~17:00
The first hourly cost points (up to 40 per accepted quote) should land around 17:00. If our jump is far below 40 × accepted quotes of that hour, look for extra gateway calls (bid-parser LLM fallback, reply-intent fallback) in the Sessions UI cost per session.

## While doing this
The setup starts changing at 17:00. Keep `cd watch && python board_watch.py` running (no key needed) to see a failed round within ~30 s.
