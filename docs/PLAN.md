# PLAN.md: 5U AI "Build the Forwarder"

> v3 · Sat 21 Nov ~13:35 · based on 5U's deep-dive slides and the challenge brief. **Tasks and owners: [`docs/TASKS.md`](TASKS.md).**
> ❓ = still open. Ask 5U on Discord `#5u-ai` and update this file with the answer.

## 1. The challenge (from the brief)
We build a **digital air forwarder**. It quotes, books and tracks shipments through **one mailbox**, on its own, through the night.
**A new air export RFQ reaches every team every 6 minutes, and each one expires 6 minutes later.**

The task:
1. Read every mail and route it: customer request, carrier bid, portal reply or tariff sheet.
2. Price the request from the **rate sheets**, the **rate portal** and **bids from 2–5 carriers**.
3. Quote **one** option, the one the customer asked for: **cheapest or fastest**.
4. **Book by rate ID** when the customer accepts, and keep the customer informed.
5. Answer tracking questions from **our own CRM**.
6. Reply **in the customer's thread**. Only our **first quote in a thread** counts.
7. Every quote states **one all-in total with its currency**.

**What we must build:**
- A Router and up to three agents: RFQ + booking, track and trace, tariff ingestion.
- A **Pricing module** that holds tariffs as structured prices, with automatic ingestion of new tariffs.
- A **CRM** with quotes and booked shipments: history, won and lost, and a dashboard.
- A **Sessions UI with streaming**, where a person steps into the autonomous system. Finding a session and intervening has to be easy.

**What 5U provides:**
| Part | Details |
|---|---|
| Start kit | **10 airline rate sheets in mixed formats**, a carrier list with airline and trucker email addresses, and the **pickup zones**. Some airlines are only in the sheets, others only on the portal. |
| Mailbox | One per team. Every mail in and out is logged. |
| Rate portal | **API** with rate IDs and booking (**rate limited; a rate ID is valid for 15 min**), a browser page behind a bot challenge (we skip it), and a desk at `ratedesk@hackloop.mail` that answers by email. |
| Customer agents | One sends RFQs and follow-ups. One asks tracking questions from `tracking@hackloop.mail`. |
| Carrier agents | **2–5 per destination** answer bid requests by email. Airlines also send **monthly tariffs**; truckers don't. |
| LLM gateway | One key per team, **OpenAI models only**, used with **our own OpenAI key**. It counts each team's cost. **A quote made without a gateway call earns no cost points.** |
| Leaderboard | Each team's score per email and in total. Who booked what stays visible. |
| API docs | Swagger for the mailbox, portal and gateway at the Base URL on our **kit card**, under `/docs`. |

**Scope:**
- In: air export RFQs only, **with a door-to-port option** (pickup by a trucker, then the flight).
- Out: building a TMS, **margins**, ocean freight, competition between teams.

**Rules:**
- Every team gets the same request at the same time and is scored on its own.
- **No second chance:** a missed or rejected request is lost.
- Only mail started by 5U's agents is scored.
- After a few hours of build time, **the setup changes about once an hour, unannounced. We learn of a change from failed quotes.**

## 2. Scoring, and what it means for the design
Each accepted quote earns up to **100 points**. A team's score is the sum over all requests.
| Part | Points | Rule |
|---|---|---|
| Price accuracy | 45 | Full at the best price, fewer the further above it |
| LLM cost | 40 | Gateway spend per accepted quote in the hour. Full at no spend, zero at **0.10 USD** |
| Response time | 15 | Full **within 2 min** of the request, zero at 6 min |

- **Accepted** = within **5% of the best price**. Only accepted quotes score.
- **Among carrier bids, the right one is the most balanced: price and speed weigh 50/50.**
- **"Read the rate sheets closely. The best price is not always the obvious one."**
- **Bonus:** +10 for a correct tracking answer on a booked shipment. +10 from the jury for the accepted email that reads most human.
- **Final ranking:** the leaderboard alone does not pick the winner. There's a final pitch of **3 min + 2 min Q&A**. The jury judges 1. the pitch, 2. UX and design, 3. the codebase, 4. how human the emails read.

Design consequences:
1. **Exactly one tiny gateway call per RFQ:** extraction with the cheapest model and a short prompt. No call means no cost points; a big call eats the 40. Everything else (routing, pricing, templates) is code. Cost per accepted quote is shown live.
2. **Quote within 2 min:** price from sheets and portal immediately, send bid requests right away, and quote at a **cut-off of ~90 s** or when all bids are in. Tune it from the leaderboard.
3. **Price exactly right:** no margin (out of scope). Pricing is plain code with tests for chargeable weight, weight breaks, minimums, surcharges and validity. The "not obvious" best price usually hides there.
4. **Pick the right option:** the customer's ask (cheapest/fastest) decides. For carrier bids, the balanced score (price and speed 50/50) decides ❓ exact formula.
5. **First reply = the quote:** never send an ack or a provisional mail. Reply in the customer's thread with one all-in total + currency.
6. **Human-sounding mail:** hand-written templates with natural wording, in the customer's language. No LLM-written replies (cost).
7. **Hourly changes:** nothing hard-coded. Tariffs come through ingestion. Every failed quote and parse error shows up in the UI and on the leaderboard watch.
8. **Go live early:** every 6 minutes we're offline is a lost request.

## 3. What we build
**Problem:** RFQs arrive around the clock, every one needs rate sheets, the portal and carrier bids checked, and only a quote within minutes at the best price wins. Nobody does that at 2 a.m.
**Solution:** an AI air forwarder that answers every RFQ in its thread within 2 minutes with the right all-in price, books by rate ID on acceptance, keeps the customer posted and answers tracking from its CRM. It spends a fraction of a cent of LLM per quote. A live Sessions UI lets a person find any session and step in.

**Demo flow:**
1. An RFQ arrives: door-to-port, "fastest".
2. The Sessions UI streams the session live:
   - routed (rules)
   - extracted (1 tiny call, cost shown)
   - sheet + portal prices ready
   - 4 carriers and 1 trucker asked, 3 bids in
   - fastest option chosen, quote sent at 1:32
3. The customer accepts. We book by rate ID and send the confirmation.
4. `tracking@` asks "where is it?" and we answer from the CRM.
5. The dashboard shows won/lost, average response time and cost per accepted quote.
6. A person opens a flagged session, pauses it and sends a corrected reply.

## 4. Components
| Component | Job | LLM? |
|---|---|---|
| Mailbox adapter | 5U mailbox API (Swagger): fetch new mails, reply in thread, attachments | no |
| Router | sorts every mail by sender + thread first: customer RFQ / follow-up / acceptance, `tracking@`, carrier bid, `ratedesk@` reply, tariff sheet | only if rules can't decide (gateway, tiny) |
| RFQ + booking agent | extract → sheet + portal prices → mail carriers (+ trucker for door-to-port) → collect bids → choose → quote in thread → on acceptance book by rate ID → confirm + status updates | 1 tiny extraction call per RFQ |
| Tracking agent | `tracking@` question → find the booked shipment → answer from the CRM (template) | no |
| Tariff ingestion | parse the 10 start-kit sheets; auto-ingest monthly airline tariffs from mail attachments into the tariffs table | code parsers per format; gateway LLM only for an unknown format |
| Pricing module | tariffs as structured prices; chargeable weight, weight breaks, minimums, surcharges, validity, pickup zones; choose cheapest / fastest / balanced | no |
| Portal client | rate lookup (rate IDs, 15-min validity) and booking; respects the rate limit with a cache | no |
| CRM | sessions = requests: quotes, bids, bookings, status, won/lost, all mails | no |
| Sessions UI | search sessions, live step stream (SSE), intervene (pause, edit + send reply), dashboard | no |
| `llm.py` | the **only** caller of the gateway; logs tokens and cost per session | — |

## 5. Edge cases (air export)
Swap in the real rules from the start-kit sheets (task U2 documents them).
- **Chargeable weight** = max(actual kg, volume kg), with volume kg = L×W×H cm ÷ divisor. The divisor comes from the sheet (often 6000).
- **Weight breaks:** use the right break, and also price at the next break's minimum, because it is sometimes cheaper. Apply the minimum charge.
- **Surcharges:** fuel and security per kg (actual or chargeable?), per-AWB fees, currency.
- **Validity:** never use an expired tariff or a portal rate ID older than 15 min.
- **Door-to-port:** pickup address → pickup zone → trucker price, added to the air price for one all-in total.
- **Cheapest vs fastest:** read the customer's ask. Transit times come from sheets, portal and bids.
- **Places:** city → airport code. Some cities have several airports.
- **Units and formats:** lbs/inches, decimal commas, "3 pcs @ 120x80x100", local dates, any language.
- **Special cargo** (dangerous goods, lithium, perishables, oversize): only carriers that accept it, else flag for a person.
- **Threads:** follow-ups attach to their session. An acceptance books the quoted rate ID, and if that rate ID has expired (>15 min) we get a fresh one ❓.

## 6. Architecture and owners
```
5U mailbox ⇄ agent/  worker: mailbox adapter → Router → RFQ+booking agent / Tracking agent
                       │ every LLM call via agent/llm.py ──► 5U LLM gateway (OpenAI)
                       │ HTTP
5U rate portal ⇄ backend/ FastAPI + SQLite: CRM/sessions, pricing module, tariff ingestion, portal client
                       │ SSE
                 frontend/ Sessions UI: search, live stream, intervene, CRM dashboard
```
The agent handles several RFQs at once (one thread per session), because bids arrive over minutes.

**Who does what.** Julien and Orhun take the token-heavy coding (agents, backend). Batu and Ulas take the UI, data, 5U contact and pitch.
| Area | Owner | Builds |
|---|---|---|
| `agent/` | **Julien** | mailbox adapter, Router, RFQ + booking agent (extraction, carrier round, quote, booking), Tracking agent, `llm.py` |
| `backend/` + root + `docs/` | **Orhun** (Lead) | FastAPI, SQLite CRM, SSE stream, pricing module, tariff ingestion, portal client, hosting it all night; CONTRACT.md, Makefile/CI, merges |
| `frontend/` | **Batu** | Sessions UI (search, live stream, intervene), CRM dashboard, UX and design |
| 5U contact, data, `pitch/` | **Ulas** | kit card, keys and start kit; rate-sheet notes; sample mails as fixtures; human-sounding mail templates; leaderboard and change watch; pitch + video |

## 7. Contract proposal (the Lead copies this into `docs/CONTRACT.md`)
A **session** is one customer request and doubles as its CRM record.

Endpoints:
- `GET /health` → `{ "ok": true }`
- `POST /api/price`: `{ "rfq": Rfq, "bids": PriceOption[] }` → `{ "options": PriceOption[], "chosen": PriceOption | null, "why": "…" }` (sheets + portal + the bids passed in)
- `POST /api/book`: `{ "session_id": 17, "rate_id": "R-123" }` → `{ "confirmation": "…" }` (portal booking)
- `POST /api/tariffs/ingest`: `{ "filename": "…", "content_base64": "…", "from": "…" }` → `{ "rows": 120 }` (agent hands over tariff attachments)
- `POST /api/sessions`: `{ "customer": "…", "thread_id": "…" }` → `{ "id": 17 }` (agent)
- `PATCH /api/sessions/{id}`: any of `stage`, `rfq`, `bids`, `quote`, `booking`, `status_updates`, `outcome`, `needs_human` (agent)
- `POST /api/sessions/{id}/events`: `Event` (agent)
- `POST /api/sessions/{id}/intervene`: `{ "action": "pause" | "resume" | "send", "body": "…" }` (frontend; the agent checks `paused` before every send and sends queued manual replies)
- `GET /api/sessions?q=…&stage=…` → `Session[]` · `GET /api/sessions/{id}` → `Session`
- `GET /api/sessions/find?thread_id=…&reference=…` → `Session | null` (agent: router and tracking)
- `GET /api/stream`: SSE, one `Event` per message (frontend)

Types:
```jsonc
// Rfq: what the customer asked for (weight_kg is per piece)
{ "origin": "MUC", "destination": "JFK", "ask": "cheapest",       // cheapest | fastest
  "pickup": { "address": "…", "zone": "Z2" },                      // null = airport delivery, else door-to-port
  "ready_date": "2026-11-23",
  "pieces": [{ "count": 3, "length_cm": 120, "width_cm": 80, "height_cm": 100, "weight_kg": 140 }],
  "commodity": "machine parts", "dangerous_goods": false,
  "customer_reference": "PO-4711", "language": "de" }

// PriceOption: one way to fly it, all-in
{ "source": "sheet",                  // sheet | portal | carrier_bid
  "carrier": "…", "rate_id": null,    // portal and bids carry a rate ID ❓ how sheet rates get booked
  "currency": "EUR", "total": 1856.00, "transit_days": 2, "valid_until": "…",
  "chargeable_weight_kg": 480,
  "breakdown": [{ "label": "Freight 480 kg × 3.20", "amount": 1536.00 },
                { "label": "Fuel 480 kg × 0.60",   "amount": 288.00 },
                { "label": "AWB fee",              "amount": 16.00 },
                { "label": "Pickup zone Z2",       "amount": 16.00 }] }

// Session (= CRM record)
{ "id": 17, "customer": "…", "thread_id": "…", "received_at": "…",
  "stage": "quoted",                  // new | pricing | quoted | booked | tracking | done | failed
  "outcome": "open",                  // open | won | lost | expired
  "rfq": { /* Rfq */ }, "bids": [ /* PriceOption */ ],
  "quote": { /* PriceOption + "sent_at" */ },
  "booking": { "rate_id": "R-123", "confirmation": "…", "booked_at": "…" },
  "status_updates": [{ "at": "…", "text": "Picked up in zone Z2" }],
  "llm_cost_usd": 0.0002, "needs_human": false, "paused": false }

// Event: one step, streamed to the UI
{ "session_id": 17, "at": "2026-11-21T02:01:32+01:00",
  "kind": "quote_sent",               // mail_in | routed | extracted | priced | carrier_asked | bid | quote_sent | accepted | booked | status_sent | tracking_answer | tariff_ingested | needs_human | intervened | error
  "text": "Quote sent: EUR 1,856.00 all-in (fastest)", "data": {}, "llm_cost_usd": 0 }
```

## 8. Stack
- **agent/** and **backend/**: Python 3.12 + uv, one uv project per folder.
  - backend: FastAPI + uvicorn, SQLite (stdlib `sqlite3`), pytest. SSE uses `StreamingResponse`, so no extra package.
  - agent: the `openai` SDK pointed at the 5U gateway (`OPENAI_BASE_URL`). Use the cheapest model that passes our extraction fixtures, with structured outputs. `httpx` for the mailbox and backend.
  - Rate-sheet parsing: libraries depend on the formats (e.g. `openpyxl`, `pdfplumber`); decide once U2 has looked at them.
- **frontend/**: Next.js + TypeScript + Tailwind + shadcn/ui, pnpm. It uses `EventSource` on `/api/stream`.
- **Ports:** backend 8000, frontend 3000.
- **Env vars** (in `.env`, never committed): `OPENAI_API_KEY` (team gateway key ❓ or our own OpenAI key), `OPENAI_BASE_URL` (gateway), `FIVEU_BASE_URL` (kit card), `MAILBOX_*`, `PORTAL_*`, `BACKEND_URL`, `LLM_MODEL`.
  - These replace `LLM_API_KEY` and `MOCK_API` in CONTRACT.md.

## 9. Timeline
Deadline **Sun 12:45** per AGENTS.md; confirm 5U's deadline ❓. Task IDs refer to `docs/TASKS.md`.
| Milestone | By | Done when | Tasks |
|---|---|---|---|
| **Now** | Sat 15:00 | Kit card, keys, Swagger docs and start kit shared with the team; first questions asked | U1 |
| **M1 Skeleton** | Sat 16:30 | A sample RFQ goes router → extraction → price from one parsed sheet → quote in thread; the session appears in the UI | L2, B1, B2, A1, A2, F1, U2 |
| **M2 Live** | Sat 18:30 | Real mailbox, portal and gateway; all 10 sheets ingested; we answer real RFQs and appear on the leaderboard | A3, B3, B4, B5, F2, U3, U4 |
| **M3 Full flow** | Sat 22:00 | Carrier and trucker bids, booking, status updates, tracking; intervene + dashboard in the UI | A4, A5, A6, F3, F4 |
| **Night** | Sat 22:00–Sun 08:00 | System runs on the host (B5). One person on watch at a time, 2-hour shifts ❓ agree in team | U5 |
| **M4 Tuned** | Sun 10:00 | Cut-off and cost tuned, fixes from failed quotes, UI polished, pitch draft | A7, F5, U6 |
| **Freeze** | Sun 12:00 | Code frozen, README and video done; submit by 12:45 | everyone |

## 10. Open questions for 5U (`#5u-ai`)
1. **Balanced choice:** how exactly are price and speed weighed 50/50 among carrier bids? When does the customer's "cheapest/fastest" apply instead?
2. **Door-to-port:** how do pickup zones and trucker prices combine into the all-in total? Do we ask truckers by email for every RFQ?
3. **Booking:** how do we book an option that comes from a rate sheet or a carrier bid (rate ID from where)? What if the rate ID expired before the customer accepts?
4. **LLM cost:** does tariff-ingestion spend count towards "spend per accepted quote"? Is LLM use outside the gateway allowed (e.g. for parsing sheets at build time)? Does the gateway call have to be tied to the RFQ?
5. **Keys:** is the gateway key the same as "our own OpenAI key"? Which models does the gateway allow?
6. **Portal:** what is the rate limit?
7. **Time:** is response time measured until our reply lands in the customer's thread?
8. **Keep informed:** which status updates does the customer expect after booking?
9. **Deadline and deliverables:** submission time, repo, video?

## 11. Rules for agents working on this
- Numbers come from code, never from the LLM.
- Every LLM call goes through `agent/llm.py` and is logged with its cost. One tiny call per RFQ is the budget.
- Never send a provisional mail to a customer: the first reply in a thread is the quote, with one all-in total + currency.
- Check `paused` before sending anything for a session.
- Build against mocks or fixtures until the real interface works. The real adapter keeps the same interface.
- Stick to the CONTRACT.md shapes, and propose changes to Orhun (Lead) instead of editing it.
