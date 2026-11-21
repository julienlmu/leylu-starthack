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
- `options`: every way to fly it, **all-in**, from the rate sheets, the portal and the `bids` passed in. For door-to-port (`rfq.pickup` not null) each air option already includes the pickup leg (cheapest trucker bid with `leg: "pickup"`, else the pickup-zone price), so `total` is what the customer pays.
- `chosen`: the one option to quote. `ask: "cheapest"` → lowest `total_eur`; `ask: "fastest"` → lowest `transit_days`, ties → lowest `total_eur`. ❓ Balanced 50/50 rule for carrier bids (PLAN.md §10.1): applied once 5U confirms the formula.
- `chosen` is `null` when nothing can be priced (the agent hands the session to a person).
- `why`: one short line for the UI, e.g. `"fastest: Kestrel 1 day, EUR 1,856.00"`.
- Never calls the LLM. Expired tariffs and portal rates older than `valid_until` are skipped.

### `POST /api/book` (agent)
`{ "session_id": 17, "rate_id": "R-abc12345" }` → `Booking` (without `booked_at`; the agent adds it)
- Books the portal rate (`POST /v1/portal/bookings` with `team_reference` = `S-<session_id>`).
- If `rate_id` is `null` (sheet option) or expired (rate IDs live 15 min), the backend first gets a fresh portal rate for the quoted airline, origin, destination and weight, then books that. ❓ PLAN.md §10.3: how 5U wants sheet and bid options booked.
- 502 with `detail` when the portal refuses; the agent then flags the session for a person.

### `POST /api/tariffs/ingest` (agent)
`{ "filename": "kestrel-airways-tariff-2026-12.xlsx", "content_base64": "…", "from": "tariffs@kestrel.example" }` → `{ "rows": 120, "airline": "Kestrel Airways", "valid_until": "2026-12-31" }`
- Parses the attachment into the tariffs table; rows from a newer file replace that airline's older rows. `rows: 0` with a `detail`-style `"error"` string when the format is unknown. Logs a `tariff_ingested` event (`session_id: null`).

### `GET /api/stream` (frontend): Server-Sent Events
- One message per `Event`: `data: <Event as JSON>\n\n`. A comment line `: ping` every 15 s keeps the connection open.
- The frontend refetches `GET /api/sessions/{id}` (or the list) when an event arrives; the stream does not carry full sessions.

## Shared types
```jsonc
// Rfq: what the customer asked for. Units are already converted by the agent (cm, kg).
{ "origin": "MUC", "destination": "JFK",          // IATA airport codes
  "ask": "cheapest",                               // cheapest | fastest (default cheapest)
  "pickup": { "address": "Industriestr. 5, 85748 Garching", "zone": null },
                                                   // null = delivered to the airport; else door-to-port.
                                                   // The agent sends zone: null, the backend resolves it from pickup_zones.csv.
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
  "rate_id": null,                    // portal rates and carrier bids carry one; sheet options don't
  "currency": "EUR", "total": 1856.00,
  "total_eur": 1856.00,               // for comparing options in different currencies (backend fills it; null if unknown)
  "transit_days": 2,                  // or null when the bid doesn't say
  "valid_until": "2026-11-21T16:15:00+00:00",   // or null
  "chargeable_weight_kg": 480,        // or null for bids
  "breakdown": [{ "label": "Freight 480 kg × 3.20", "amount": 1536.00 },
                { "label": "Fuel 480 kg × 0.60",   "amount": 288.00 },
                { "label": "AWB fee",              "amount": 16.00 },
                { "label": "Pickup zone Z2",       "amount": 16.00 }] }
// Bids from the agent carry only source, leg, carrier, rate_id, currency, total, transit_days; the rest may be missing.

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
  "bids": [],                         // PriceOption[] from the carrier round
  "quote": null,                      // PriceOption + "sent_at", once sent
  "booking": null,                    // Booking once booked
  "status_updates": [{ "at": "…", "text": "Booking BK-1A2B3C4D confirmed by the airline" }],
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

`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_API_KEY` and `MOCK_API` are no longer used.
