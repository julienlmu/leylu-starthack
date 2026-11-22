# Leylü: the night-shift freight forwarder

**START Hack Munich 2026 · 5U AI challenge "Build the Forwarder".**
Every 6 minutes for 24 hours, 5U mails us a customer request for an air-freight quote. Leylü reads it in any
language, asks the carriers, prices it in code, sends one all-in quote, books it when the customer says yes, and
answers "where is my cargo?" from its own CRM. A person watches everything in the Sessions UI and can step in.

## Live results (CRM export, Sat 21 Nov 16:00 to Sun 22 Nov 10:15 Berlin)

| | |
|---|---|
| Customer requests handled | **189** (720 mails in) |
| Quotes accepted and booked | **130** (69 %) |
| Median time to first reply | **38 s** (mean 53 s) |
| LLM cost | **$0.085 in total**: ≈ $0.0005 per request, ≈ $0.00012 per mail |
| Routed by rules, no LLM | 187 of 189 requests |
| Carrier bids collected | 2,053 |
| Tracking questions answered from the CRM | 122 |
| Board rank | [#_ of 14, ___ points] (fill in at 12:00 from `/v1/board`) |

## How it works

```
5U mailbox ─▶ router (rules, $0) ─┬─▶ RFQ agent ─▶ extract (one small LLM call, strict JSON, numbers checked in code)
                                  │                 ─▶ carriers asked in parallel (airlines of the lane + truckers)
                                  │                 ─▶ price in code (rate sheets + 5U portal + bids)
                                  │                 ─▶ quote gate (fit, DG, deadline, one amount) ─▶ quote mail
                                  ├─▶ booking agent  "yes" ─▶ book by rate ID, exactly once ─▶ confirmation
                                  ├─▶ tracking agent "where is it?" ─▶ answer from the CRM
                                  └─▶ silent close   lookalike sender, thanks after a decline, spam
                                         │
              backend: FastAPI + SQLite CRM (sessions, events, quotes, bookings, rate memory)
                                         │
              frontend: Next.js Sessions UI (live agent trace per mail, person queue, pause and intervene, dashboard)
```

**Rules first, LLM only for the leftovers.** The router is plain code. One small model call (`gpt-6-luna`, reasoning
off) reads the fields rules can't; a stronger model re-reads only the mails that fail the code checks. Every number
a customer sees (chargeable weight, weight breaks, minimums, surcharges, FX, margins) comes from tested Python, never
from the model. Cost is 40 of 100 points per quote, so this matters.

## The traps we handled live

| Trap | What Leylü does |
|---|---|
| Lookalike sender (`nordlicht-audio` vs `nordlicht.audio`) | Nothing sent, nothing booked, session closed |
| Import / foreign origin airport | Polite decline based on the origin airport |
| "A competitor is 7 % cheaper, can you match?" | Best real price from our own bids, never below cost; same service kept |
| Rate portal down (503) | Form fallback and remembered portal rates |
| Portal surge (all airlines ×1.15 / ×1.30 for ~30 min) | Factor detected, cached rates rescaled |
| Several shipments in one RFQ | Each lot priced on its own |
| Cancellation before / after booking | "Nothing booked yet" / cancelled with the airline |
| Missing weight, origin or pickup | One short question in the customer's language, quote follows in the same thread |
| "Same shipment as my earlier request" | Earlier request found by subject, lane and time |
| Packing list disagrees with the mail | Packing-list totals used, said in the quote |
| All carriers refuse the lane | Clear decline instead of a guessed price |
| Price near a weight break | The break is priced when it is cheaper |

Every new rule was replayed against all past sessions before it went live.

## Repo map

| Folder | What is in it |
|---|---|
| [`agent/`](agent/README.md) | The worker: mailbox, router, RFQ / booking / tracking agents, templates, evals and ~120 test files |
| `backend/` | FastAPI: CRM, pricing engine, tariff ingestion, portal client and memory, booking |
| `frontend/` | Next.js Sessions UI and CRM dashboard |
| `pitch/` | Pitch script, demo video script and shot list |
| `docs/` | Contract between modules, decisions, live status, traps we expected and saw |

## Run it

```bash
make setup          # uv + pnpm installs, git hooks
make dev            # backend :8000 + Sessions UI :3000
make agent-mock     # agent on fixture mails, nothing is sent
make check          # lint + typecheck + tests (what CI runs)
```

`make live` runs backend, live agent and UI together with restarts; it needs `FIVEU_API_KEY` in `.env`. Only one
machine may run it against the 5U mailbox (see `docs/LIVE_STATUS.md`).

## Team

Orhun · Julien · Batu · Ulas
