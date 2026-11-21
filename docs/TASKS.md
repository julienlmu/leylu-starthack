# TASKS.md
Status: TODO / DOING / REVIEW / DONE. Only edit rows in your own section.
To claim a task: set DOING + branch name, commit just this file, push (`SKIP_PUSHLOG=1 git push`).
Plan, contract proposal and milestones: `docs/PLAN.md`. Milestones: **Now** Sat 15:00 · **M1** Sat 16:30 skeleton · **M2** Sat 18:30 live on the leaderboard · **M3** Sat 22:00 full flow · **M4** Sun 10:00 tuned + pitch draft · **Freeze** Sun 12:00.

Split: Julien and Orhun take the token-heavy coding. Batu and Ulas take the UI, data, 5U contact and pitch.

## Orhun: Lead + backend (`backend/`, root, `docs/`)
| ID | Task | Due | Status | Branch |
|---|---|---|---|---|
| L1 | Repo skeleton, CI, branch protection | — | DONE | lead/L1-skeleton |
| L2 | Copy the contract from PLAN.md §7 into CONTRACT.md; fill in the Makefile (uv + pnpm), CI (`setup-uv`, pnpm) and AGENTS.md commands | M1 | REVIEW | orhun/L2-contract-make-ci |
| B1 | FastAPI + SQLite CRM: sessions, events, intervene, search, SSE `/api/stream` | M1 | REVIEW | orhun/B1-crm-api |
| B2 | Pricing module: tariffs table; chargeable weight, weight breaks, minimums, surcharges, validity, pickup zones; choose cheapest / fastest / balanced; tests. Uses U2's notes | M1 | REVIEW | orhun/B2-pricing |
| B3 | Tariff ingestion: parsers for the 10 start-kit sheets; `POST /api/tariffs/ingest` for monthly airline tariffs from mail | M2 | REVIEW | orhun/B3-tariff-ingest |
| B4 | Portal client: rate lookup with rate IDs (15-min validity, rate-limit cache) and `POST /api/book` | M2 | REVIEW | orhun/B4-booking |
| B5 | Hosting: run backend + agent all night (always-on machine or VM), auto-restart, logs | M2 | REVIEW | orhun/B5-live-runner |
| L3 | Integration and merges, keep `main` green | ongoing | TODO | |

## Julien: agents (`agent/`)
| ID | Task | Due | Status | Branch |
|---|---|---|---|---|
| A1 | `llm.py`: gateway wrapper (OpenAI SDK, structured output, cost log per session). Pick the cheapest model that passes the fixtures. One tiny call per RFQ | M1 | DONE | julien/A1-A2-agent-core |
| A2 | Mailbox adapter (5U mailbox API, fixtures until access) + rules-first Router: RFQ / follow-up / acceptance / `tracking@` / carrier bid / `ratedesk@` / tariff sheet | M1 | DONE | julien/A1-A2-agent-core |
| A3 | RFQ agent MVP: extract → `POST /api/price` → quote in the customer's thread with one all-in total + currency, using templates; session events | M2 | DONE | julien/A3-rfq-agent |
| A4 | Carrier round: mail 2–5 carriers (+ trucker for door-to-port), parse bids, re-price, quote at the ~90 s cut-off | M3 | DONE | julien/A4-carrier-round |
| A5 | Booking: acceptance → `POST /api/book` by rate ID → confirmation + status updates to the customer | M3 | DONE | julien/A5-A6-booking-tracking |
| A6 | Tracking agent: `tracking@` questions → answer from the CRM (+10 per correct answer) | M3 | DONE | julien/A5-A6-booking-tracking |
| A7 | Tuning: cut-off, extraction misses, cost per quote; react to hourly changes from failed quotes | M4 | TODO | |

## Batu: frontend + UX (`frontend/`)
| ID | Task | Due | Status | Branch |
|---|---|---|---|---|
| F1 | Next.js + shadcn Sessions UI on mock data (shapes from PLAN.md §7): session list with search/filter, session detail (mail thread, extracted request, options, quote, booking) | M1 | REVIEW | batu/F1-sessions-ui |
| F2 | Live updates: `EventSource('/api/stream')`, steps appear as they stream | M2 | TODO | |
| F3 | Intervene: pause/resume a session, edit and send a reply by hand, "needs a person" queue | M3 | TODO | |
| F4 | CRM dashboard: quotes history, won/lost, booked shipments, average response time, cost per accepted quote | M3 | TODO | |
| F5 | UX and design polish (jury criterion 2), screenshots for the pitch | M4 | TODO | |

## Ulas: 5U contact, data, pitch (`pitch/`, fixtures with the folder owner's OK)
| ID | Task | Due | Status | Branch |
|---|---|---|---|---|
| U1 | **Now:** kit card → Base URL, Swagger (`/docs`) for mailbox/portal/gateway, keys into everyone's `.env` (never committed); share the start kit (10 rate sheets, carrier list, pickup zones); ask the PLAN.md §10 questions and write the answers there | Now | TODO | |
| U2 | Read the 10 rate sheets by hand: write up each format and its traps (breaks, minimums, surcharges, divisor, validity, "best price not obvious") in `docs/RATES.md`, with 3 worked examples and the correct totals | M1 | TODO | |
| U3 | Sample mails: save real RFQs, bids, `ratedesk@` replies and tracking questions with the expected result as fixtures in `agent/fixtures/` (the eval set) | M2 | TODO | |
| U4 | Human-sounding mail templates: quote, booking confirmation, status update, tracking answer, carrier bid request, `ratedesk@` request; languages as seen in the RFQs (jury +10 and criterion 4) | M2 | TODO | |
| U5 | Leaderboard + `#5u-ai` watch: log failed quotes and every hourly change in `docs/CHANGES.md`, alert the owner; organise the night watch | ongoing | TODO | |
| U6 | Pitch deck (3 min + 2 min Q&A), demo script, backup demo video, README | M4 | TODO | |
