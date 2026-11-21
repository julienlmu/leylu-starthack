# Fixes for Orhun: live machine, backend, ops

> Sat 21 Nov ~16:15 · collected from the reviews of #14–#21, #30 (deploy-live) and the first live round. Everything here
> was reproduced in a review (fake portal, local backend, dry runs) unless it says otherwise. Agent-side fixes are
> already on `main`. Tick items off here or in your push log.

## P0: now, on the live Mac (every 6-minute round counts)
1. **Run what's on `main`.** Round 1 (#269, Bergisch Gladbach → ORD, fastest, door-to-port) got no answer: the mail named
   no departure airport, so the agent handed it to a person as "missing: origin". `main` fixes that (#33: origin from the
   pickup zone, 51 → CGN) and brings the real carrier list (#31: 29 airlines by destination, truckers by pickup zone, a
   failed send to one carrier no longer kills the RFQ). Checked with the real mail: nothing missing, 11 airlines + 4
   zone-51 truckers asked.
   - `git merge origin/main` into `orhun/deploy-live`
   - remove `CARRIERS_FILE=no-carriers.json` from the live env
   - restart: `kill $(cat logs/live.lock/pid)`, then `make live`
   - watch `logs/agent.log` on the next RFQ: `carrier_asked` with names, then `bid` lines, then `quote_sent`
2. Update `docs/LIVE_STATUS.md` (carriers on, which commit runs).

## P1: before leaving it alone overnight
3. **One bad tariff file crash-loops the backend.** `app.py:73` loads every file in the ingest dir via
   `Tariffs.from_files` with no per-file error handling, and `app.py:194` writes the file in place (not atomic). A save
   cut off by a kill/restart leaves truncated JSON, `import app` raises `JSONDecodeError`, and `live.sh` restarts the
   backend forever (reproduced). Fix: skip + log unreadable files in `from_files`; write to a temp file + `os.replace`.
   Test: a truncated JSON in a temp ingest dir → app still starts.
4. **Bad tariff dates replace good sheets.** `ingest.py:75-83` `_date` doesn't validate: `11/30/2026` (US order) becomes
   `2026-30-11`, is accepted, replaces the good November sheet and is saved (reproduced). Fix: `date.fromisoformat()` on
   the result (try day/month, then month/day), reject when invalid or `valid_from > valid_to`.
5. **Double booking, last narrow case.** `booking.py:27-35`: after a 410 the fresh rate gets booked; if the portal books
   it but its answer is lost (timeout), we return 502 and store nothing, and the next acceptance books *another* fresh
   rate (reproduced with the fake portal: BK-1 and BK-2). Bookings are public and can't be cancelled. Fix: store the
   fresh `rate_id` on the session before booking it and retry that same id first (the portal answers 200 to a repeat).
6. **Door-to-port without a trucker bid gets no quote.** `pricing.py` returns `chosen: null` when no pickup leg arrived
   by the cut-off. We don't know yet how fast 5U's truckers answer. Options: a fallback pickup price per zone (e.g. the
   last trucker bid seen for that zone), and/or the agent waits longer for the first pickup bid on door-to-port RFQs
   (Julien can add that in `agent/`). Decide after the first rounds with carriers on.
7. **Manual reply + agent quote = two quotes.** `POST /api/sessions/{id}/intervene` `send` doesn't set `paused`. Batu's UI
   now pauses first, but set `paused=true` server-side before sending too (the agent checks `paused` before every send).
8. **CORS is open to everyone.** `app.py:78` `allow_origins=["*"]` on an API whose `intervene send` mails real customers.
   The UI goes through the Next proxy (same origin), so `["http://localhost:3000"]` is enough.
9. **`make agent-mock` on the live Mac writes into the live CRM.** It posts fixture sessions to `BACKEND_URL` (default
   :8000 = the live backend there). Point agent-mock at another port/backend, or warn in the Makefile.
10. **Price deadline misses the lane list.** `_portal_options` waits for the airline/lane list (`/ports`, 8 s timeout)
    before the 5 s deadline starts: worst case ~13 s. Fine today (the agent waits 30 s for `/api/price`), but include it
    in the deadline.

## P2: correctness and cleanup
11. `booking.py:31-32`: the +5 % fresh-rate guard compares the fresh *air-only* total with the quoted *all-in* total
    (incl. pickup), so it's looser than 5 % for door-to-port. Compare with the quote's air part.
12. A USD bid is skipped after a restart until some portal rate states an fx rate. Persist the last fx (or a fallback).
13. `ingest.py:150`: `int(numbers[0])` cuts fractional transit days (1.5 → 1).
14. `app.py:66`: `TariffIn.sender` rejects `"from": null` with 422; make it optional.
15. `crm.py:141` `_haystack`: one session with a non-dict `rfq` makes every `GET /api/sessions?q=` return 500.
16. Booking tests missing: a 200 retry, 503, and 410 without a fresh rate.
17. `scripts/deploy.sh`:
    - the tar (l. 23-24) still copies `.claude/worktrees/*`, each with its own `.env` copy (bsdtar happens to skip
      nested `.env`, GNU tar doesn't): add `--exclude=./.claude/worktrees` or ship `git ls-files`
    - l. 35 installs uv with pip `--user`, which fails on Debian 12 / Ubuntu 23.04+ (externally managed Python) and
      aborts the deploy: use the astral installer
    - no `LIVE_AGENT` pass-through (no backend-only dry deploy); the health check hard-codes :8000
18. `scripts/live.sh` exits with 143 after its own `kill 0` instead of 1/130 (cosmetic).
19. Docs:
    - `CONTRACT.md:134` still says the agent doesn't send mail data. Since #24 it sends `{from, to, subject, body}` on
      mail_in, quote_sent (+ `option`), booked (+ the booking), status_sent, tracking_answer.
    - `backend/AGENTS.md` and the `app.py` docstring run uvicorn without `--timeout-graceful-shutdown 1`.
    - `PLAN.md` §8 still lists unused env vars (OPENAI_*, MAILBOX_*, PORTAL_*).

## Already done on `main` (no action)
Agent: retry on backend blips, bounded LLM calls, mail data in events, `received_at`, one booking per session
(agent side), one live worker per machine, expired RFQs skipped, bid parser ignores quoted text, all kit tariff formats
forwarded, real carrier list, origin from pickup zone. Backend/ops: the #16 time bomb, double booking after 410,
price deadline, ready-date clamp, live.sh traps/port check/health gate, SSE graceful shutdown.
