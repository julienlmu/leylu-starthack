# CONTRACT.md: interfaces between modules
Single source of truth for `agent/` ⇄ `backend/` ⇄ `frontend/`. Changes only via a PR approved by the Lead (Orhun). Agents never edit this file directly: propose the change in your push log "Contract/API changes".

Based on PLAN.md §7, plus what the merged agent (A1–A6) and frontend (F1) already send and read. Where the two differed, this file follows the code and says so.

Backend: FastAPI on `http://localhost:8000` (`BACKEND_URL`). JSON in and out, UTF-8. Times are ISO 8601 with offset (`2026-11-21T16:00:00+00:00`). Money is a JSON number with two decimals. Errors are FastAPI's `{ "detail": "…" }` with a 4xx/5xx status.

## Who calls what
| Endpoint | Called by | Built in |
|---|---|---|
| `GET /health` | everyone | B1 |
| `POST /api/sessions`, `PATCH /api/sessions/{id}`, `POST /api/sessions/{id}/events`, `GET /api/sessions/find` | agent | B1 |
| `GET /api/sessions`, `GET /api/sessions/{id}`, `GET /api/sessions/{id}/events`, `GET /api/stream` | frontend (agent reads `GET /api/sessions/{id}`) | B1 |
| `POST /api/sessions/{id}/intervene` | frontend | B1 (send: B1 + F3) |
| `POST /api/price` | agent | B2 (+ B4 for portal rates) |
| `POST /api/tariffs/ingest` | agent | B3 |
| `POST /api/book` | agent | B4 |

## Endpoints

### `GET /health` → `{ "ok": true }`

### Sessions (CRM)
A **session** is one customer request and doubles as its CRM record.

- `POST /api/sessions`
  `{ "customer": "buyer@acme.example", "thread_id": 1042, "received_at": "…" }` → `{ "id": 17 }`
  `received_at` is optional (the RFQ mail's date; default: now). New sessions start at `stage: "new"`, `outcome: "open"`.
  `thread_id` is the id of the thread's first mail (5U ids are integers; fixture ids may be strings). It comes back as sent: digits as an integer, anything else as a string.
- `PATCH /api/sessions/{id}` → the updated `Session`
  Body: any subset of `stage`, `outcome`, `rfq`, `bids`, `quote`, `booking`, `status_updates`, `llm_cost_usd`, `needs_human`, `paused`.
  Each field given **replaces** the stored value (no deep merge): send the whole `booking` dict and the whole `status_updates` list. `llm_cost_usd` is the session's running total, not an increment.
- `POST /api/sessions/{id}/events`: an `Event` → `{ "ok": true }`. Stored and pushed to `/api/stream`.
- `GET /api/sessions?q=…&stage=…&needs_human=true` → `Session[]`, newest first.
  `q` matches customer, `#id`, origin/destination, customer reference, carrier, rate ID and booking reference.
- `GET /api/sessions/{id}` → `Session` (404 if unknown).
- `GET /api/sessions/{id}/events` → `Event[]`, oldest first (history; the SSE stream only carries what happens after the page opens).
- `GET /api/sessions/find?thread_id=…` or `?reference=…` → `Session | null` (200 with `null` when nothing matches).
  `thread_id` matches exactly. `reference` matches, case-insensitive, `booking.booking_reference` (`BK-…`), `booking.rate_id`, `quote.rate_id` or `rfq.customer_reference`. The newest matching session wins.

### `POST /api/sessions/{id}/intervene` (frontend)
`{ "action": "pause" | "resume" | "send", "body": "…" }` → the updated `Session`
- `pause` / `resume` set `paused`. The agent reads `GET /api/sessions/{id}` and checks `paused` right before every mail it sends for that session; a paused session gets no automatic mail.
- `send` (needs `body`): the backend sends `body` as a reply in the customer's thread through the 5U mailbox (`POST /v1/mailbox/messages`, `in_reply_to` = the session's `thread_id`), sets `needs_human: false` and logs an `intervened` event with the mail in `data`.
- Every action logs an `intervened` event.

### `POST /api/price` (agent)
`{ "rfq": Rfq, "bids": PriceOption[] }` → `{ "options": PriceOption[], "chosen": PriceOption | null, "why": "…" }`
- `options`: every way to fly it, **all-in, in EUR**, sorted by `total`: one per sheet airline (its cheapest break, own bracket or a higher one), one per portal airline (same next-break check, within the rate limit) and every air bid passed in. Portal totals in another currency are converted with the `fx_eur_per_usd` the portal states; bids in a currency with no known rate are skipped.
- Door-to-port (`rfq.pickup` not null): the pickup zone (first two digits of the German postcode) decides the origin airport, and each air option includes the trucker's pickup (the `leg: "pickup"` bid chosen 50/50 on price and days), so `total` is what the customer pays. **There are no zone prices in the kit: without a trucker bid there is no all-in price and `chosen` is `null`.**
- `chosen`: the one option to quote. `ask: "cheapest"` → lowest total, ties → faster; `ask: "fastest"` → fewest `transit_days`, ties → cheaper. On a lane priced only by airline bids, the balanced choice (price and days 50/50) applies. ❓ PLAN.md §10.1: exact 50/50 formula (env `BALANCED_FORMULA`, `PICKUP_CHOICE`, `BIDS_ONLY_CHOICE` switch it without a deploy of code).
- `chosen` is `null` when nothing can be priced (the agent hands the session to a person).
- `why`: one short line for the UI, e.g. `"cheapest: Wayzata Air Cargo (sheet) 4 d, EUR 314.00; 4 air options (sheet 2, portal 2, bids 0)"`.
- Never calls the LLM. Sheets not valid on `ready_date` (or today) are skipped.
- Portal: **10 rate calls per team per minute** (seen live). The backend asks the portal as soon as the agent PATCHes the session's `rfq`, during the bid round, so `/api/price` at the cut-off is answered from cache. Portal rate IDs live about **10 minutes** (`valid_until`).

### `POST /api/book` (agent)
`{ "session_id": 17, "rate_id": "R-abc12345" }` → `Booking` (without `booked_at`; the agent adds it). `rate_id: null` = the session's quoted `rate_id`.
- Books the portal rate (`POST /v1/portal/bookings` with `team_reference` = `S-<session_id>`) and stores it as the session's `booking` at once. **One booking per session:** a second call returns the stored booking (two "yes" mails, retries). The agent's later PATCH that adds `booked_at` replaces it as usual.
- Expired rate (portal 410; rate IDs live about 10 min) or a rate already booked by another session (409): the backend gets a fresh rate from the quoted airline on the same lane, at the weight the quote was billed at, books it if it costs at most 5 % more than the quote, and logs a `priced` event with both rate IDs and prices. Booked rates leave the rate cache.
- 502 with `detail` when it can't book: an option without a portal rate ID (sheet or bid: ❓ PLAN.md §10.3, book by email with the airline), portal 404/409/503, or the portal is unreachable. The agent then flags the session for a person. 404 for an unknown session.

### `POST /api/tariffs/ingest` (agent)
`{ "filename": "kestrel-airways-tariff-2026-12.xlsx", "content_base64": "…", "from": "kestrel-airways@hackloop.mail" }` → `{ "rows": 18, "airline": "Kestrel Airways", "valid_until": "2026-12-31" }`
- Reads the layouts of the 10 start-kit sheets (xlsx, pdf, docx, txt, csv) with code, no LLM. The new sheet is used for every RFQ whose `ready_date` falls in its validity; a sheet of the same airline with the same `valid_from` is replaced. It is saved in `backend/data/ingested/` and loaded again after a restart.
- Not readable (an image like Danube's photos, an unknown layout, a broken file) → `{ "rows": 0, "error": "…" }`; the old sheets stay in use.
- Both cases log a `tariff_ingested` event with `session_id: null` (shown on the stream).

### `GET /api/stream` (frontend): Server-Sent Events
- One message per `Event`: `data: <Event as JSON>\n\n`. A comment line `: ping` every 15 s keeps the connection open.
- The frontend refetches `GET /api/sessions/{id}` (or the list) when an event arrives; the stream does not carry full sessions.

## Shared types
```jsonc
// Rfq: what the customer asked for. Units are already converted by the agent (cm, kg).
// The agent stores the extraction before it checks what is missing, so any field below can be null.
{ "origin": "MUC", "destination": "JFK",          // IATA airport codes
  "ask": "cheapest",                               // cheapest | fastest (default cheapest)
  "pickup": { "address": "Industriestr. 5, 85748 Garching", "zone": null },
                                                   // null = delivered to the airport; else door-to-port.
                                                   // zone = first 2 digits of the postcode ("85"); the agent may send null,
                                                   // the backend reads it from the address (data/pickup_zones.csv).
  "ready_date": "2026-11-23",                      // or null
  "pieces": [{ "count": 3, "length_cm": 120, "width_cm": 80, "height_cm": 100, "weight_kg": 140 }],
                                                   // weight_kg is PER PIECE; dims may be null when volume_m3 is given
  "volume_m3": null,                               // total volume when the RFQ gives one instead of dims (added by A3)
  "commodity": "machine parts", "dangerous_goods": false,
  "customer_reference": "PO-4711",                 // or null
  "language": "de" }                               // ISO 639-1, for the reply template

// PriceOption: one way to fly it, all-in
{ "source": "sheet",                  // sheet | portal | carrier_bid
  "leg": "air",                       // air | pickup. Only carrier bids from truckers are "pickup"; options from /api/price are always "air" (pickup included)
  "carrier": "Kestrel Airways",
  "airline_code": null,               // portal options only ("GN")
  "rate_id": null,                    // portal rates and carrier bids carry one; sheet options don't
  "currency": "EUR", "total": 1856.00,
  "total_eur": 1856.00,               // = total (options from /api/price are in EUR)
  "transit_days": 2,                  // days, may be fractional (bids in hours); null when the bid doesn't say; door-to-port includes the pickup days
  "valid_until": "2026-11-30",        // sheet: last valid day; portal: rate ID expiry (ISO time); or null
  "chargeable_weight_kg": 480,        // max(actual kg, cbm × 167); or null for bids
  "billed_weight_kg": 500,            // the weight it is billed at (a higher break when that is cheaper)
  "breakdown": [{ "label": "Freight 500 kg × 2.20",  "amount": 1100.00 },
                { "label": "Fuel 500 kg × 1.19",     "amount": 595.00 },
                { "label": "Security 500 kg × 0.14", "amount": 70.00 },
                { "label": "Pickup zone 85 (Ingolstadt) by Odenwald Cargo", "amount": 91.00 }],
  "pickup": { "carrier": "Odenwald Cargo", "rate_id": null, "total": 91.00, "transit_days": 1 } }  // door-to-port only
// Bids from the agent carry only source, leg, carrier, rate_id, currency, total, transit_days; the rest may be missing.
// The breakdown amounts always add up to total.

// Booking: the portal's BookingOut + booked_at (PLAN.md's "confirmation" field is replaced by these)
{ "booking_reference": "BK-1A2B3C4D", "team_reference": "S-17", "rate_id": "R-abc12345",
  "airline": "Kestrel Airways", "airline_code": "KE",
  "price": "1856.00", "currency": "EUR",       // price is a decimal string, as the portal sends it
  "status": "booked",                          // booked → confirmed (when the airline's confirmation mail arrives)
  "booked_at": "2026-11-21T16:09:12+00:00" }

// Session (= CRM record)
{ "id": 17, "customer": "buyer@acme.example", "thread_id": 1042, "received_at": "…",
  "stage": "quoted",                  // new | pricing | quoted | booked | tracking | done | failed
  "outcome": "open",                  // open | won | lost | expired
  "rfq": null,                        // Rfq once extracted
  "bids": [],                         // PriceOption[] from the carrier round; always a list, never null
  "quote": null,                      // PriceOption + "sent_at", once sent
  "booking": null,                    // Booking once booked
  "status_updates": [{ "at": "…", "text": "Booking BK-1A2B3C4D confirmed by the airline" }],  // always a list
  "llm_cost_usd": 0.000133,           // running total for this session
  "needs_human": false, "paused": false,
  "updated_at": "…" }

// Event: one step, streamed to the UI
{ "session_id": 17,                   // null for events without a session (tariff_ingested)
  "at": "2026-11-21T16:01:32+00:00",
  "kind": "quote_sent",
  "text": "Quote sent: EUR 1,856.00 all-in (fastest)",
  "data": {},                         // free-form; see below
  "llm_cost_usd": 0 }                 // LLM spend of this step (0 for code-only steps)
```

Event kinds: `mail_in` · `routed` · `extracted` · `priced` · `carrier_asked` · `bid` · `quote_sent` · `accepted` · `declined` · `booked` · `status_sent` · `tracking_answer` · `tariff_ingested` · `needs_human` · `intervened` · `error`.
(`declined` was added by A5.)

Event `data`:
- Mail events (`mail_in`, `quote_sent`, `status_sent`, `tracking_answer`, `intervened` with `send`) carry the mail: `{ "from": "…", "to": "…", "subject": "…", "body": "…" }` so the UI can show the thread. ⚠️ Agent: not sent yet (F1 heads-up).
- `extracted`: the `Rfq`. `priced`: the `/api/price` response. `bid`: the `PriceOption`. `booked`: the `Booking`.

## Env vars (root `.env`, never committed; names in `.env.example`)
| Var | Used by | Meaning |
|---|---|---|
| `FIVEU_BASE_URL` | agent, backend | 5U API, default `https://api.start-hack.5u.ai` |
| `FIVEU_API_KEY` | agent, backend | team key from the kit card (header `X-API-Key`) for mailbox, portal, gateway |
| `GATEWAY_OPENAI_KEY` | agent (`setup_5u.py` only) | our OpenAI key, stored once in the 5U gateway. Nothing calls OpenAI directly |
| `LLM_MODEL` | agent | gateway model, default `gpt-4o-mini` (must be in `agent/llm.py` `PRICES`) |
| `BACKEND_URL` | agent, frontend | default `http://localhost:8000` |
| `PORT` | backend | default `8000` (frontend runs on 3000) |
| `DB_PATH` | backend | SQLite file, default `backend/crm.sqlite3` |
| `BID_CUTOFF_SECONDS` | agent | quote cut-off after the RFQ, default `90` |
| `MOCK`, `FIXTURE_INBOX`, `CARRIERS_FILE`, `SINCE_ID_FILE` | agent | local runs on fixtures; see `agent/AGENTS.md` |
| `PORTAL_RESERVE` | backend | portal calls per minute kept free for must-have lookups, default `3` (optional next-break checks stop there) |
| `PICKUP_CHOICE`, `BIDS_ONLY_CHOICE` | backend | how to pick among trucker bids / airline bids on bid-only lanes: `balanced` (default), `cheapest`, `fastest` |
| `BALANCED_FORMULA` | backend | `ratio` (default: 0.5·price/best + 0.5·days/best) or `minmax` (both scaled 0–1) |

`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_API_KEY` and `MOCK_API` are no longer used.
