# Pitch: 3 min + 2 min Q&A (draft v1, U6)

Jury criteria, in their order: 1. pitch, 2. UX and design, 3. codebase, 4. how human the emails read.
Fill the `[ ]` numbers from the leaderboard and the dashboard on Sunday morning.

## Script (~3:00)

**0:00 Hook (20 s)**
"It's 2 a.m. An RFQ lands: three pallets, Munich to New York, fastest option. A human forwarder is asleep.
Ours answered in [1:32], at the best price, for a fraction of a cent. It did that [N] times tonight."

**0:20 The problem (25 s)**
Freight forwarding runs on email. Every RFQ means checking rate sheets, a rate portal and bids from several carriers,
by hand. Overpriced: deal gone. Too slow: someone else got it. One missed detail: the cargo doesn't fit.

**0:45 What we built (35 s)**
One mailbox, every kind of mail. A rules-first router sorts it; three agents do the work:
- RFQ + booking agent: reads the request in any language, asks 2–5 carriers, prices it, quotes, books by rate ID.
- Tracking agent: answers "where is it?" straight from our CRM.
- Tariff ingestion: new airline rate sheets go into the pricing module automatically.

**1:20 Live demo (60 s)** — see the demo script below. Sessions UI on screen the whole time.

**2:20 Why it wins (30 s)**
- Numbers come from code, never from the LLM. One tiny model call per RFQ: [$0.000X] per quote, so close to full cost points.
- Pricing in tested code: chargeable weight, weight breaks, minimums, surcharges, which is where "the best price is not the obvious one".
- When 5U changed the setup every hour, we saw it in the UI from the failed quotes and adapted in [X] min.
- Every email is hand-written and in the customer's language.

**2:50 Close (10 s)**
"[N] RFQs, [X]% accepted, average reply [1:xx], [$0.000X] per quote. At 2 a.m., our forwarder answers."

## Demo script (60 s, backup video if live fails)
1. Sessions UI: an RFQ arrives live (door-to-port, "fastest"). Steps stream in: routed → extracted (cost shown) → sheet + portal prices → carriers asked → bids in.
2. Quote sent at [1:32]: open the email; one all-in total, reads human.
3. Customer accepts → booked by rate ID → confirmation in the same thread.
4. `tracking@` asks for the status → answered from the CRM.
5. Dashboard: won/lost, average response time, cost per accepted quote.
6. Intervene: open a flagged session ("needs a person"), pause it, send a corrected reply by hand.

## Final numbers (5U board and CRM, Sun 22 Nov 12:30)
| Metric | Value |
|---|---|
| RFQs answered / received | 194 of 199 board rounds answered; 207 requests, 788 mails in (CRM export, Sun 12:06) |
| Accepted quotes (within 5%) | 170 on the board; all of the last 15 rounds accepted |
| Average response time | median 42 s on the board (41 s in the CRM), 92 % inside 2:00 |
| LLM cost per accepted quote | $0.095 for 207 requests ≈ $0.0005 per request; $0.12 of the $20 credit for the whole challenge |
| Tracking answers correct | 136 tracking answers scored the +10 bonus |
| Hourly changes caught + time to fix | lookalikes, imports, price match, portal 503 + surge, multi-lot, cancellations, missing info (see README) |
| Leaderboard rank | **#3 of 15, 18,811 points** (final) |

Deck: `final_pitch_html.html` (PDF: `Leylu-final-pitch.pdf`). Demo video: https://youtu.be/U356QQbyHFs
Submission checklist: `SUBMISSION.md`.

## Q&A prep
- **Why so little LLM?** Cost is 40 of 100 points per quote, and the LLM can't be trusted with numbers. It only reads the mail; code prices it.
- **What if the extraction is wrong?** Missing or unclear fields → "needs a person" in the Sessions UI, no wrong quote sent.
- **How do you handle new tariff formats?** Known layouts → cached parser; unknown → one small LLM call to map the columns, then code.
- **How did you find the hourly changes?** Failed quotes on the leaderboard + error events in the UI; logged in `docs/CHANGES.md`.
- **Why one option, not three?** The brief: quote the one the customer asked for (cheapest or fastest); only the first quote counts.
- **What would you build next?** Learning from won/lost quotes, more languages, a real TMS hand-off.
- Full list (about 45 questions, who answers what, today's numbers): [`QA.md`](QA.md)

## Slides (keep to 5)
1. Hook: "At 2 a.m. an RFQ lands. Who answers?" + our headline numbers
2. Problem: email chaos (one RFQ → sheets, portal, 5 carriers)
3. Architecture: mailbox → router → 3 agents → pricing / CRM → Sessions UI (one diagram)
4. Live demo (switch to the UI)
5. Results + why it wins (numbers table)
