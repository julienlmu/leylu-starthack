# The agent: an air forwarder that quotes in ~40 seconds for $0.00012

Every 6 minutes 5U mails us a request for an air-freight quote. Only the first priced reply in the thread counts. It must
come within 2 minutes and within ±5 % of the best all-in price, and it should cost as little LLM as possible. This
folder is the worker that does that: it reads the mailbox, asks carriers, prices, quotes, books and answers tracking
questions.

## How one request flows

```
mail ─▶ router (rules, $0) ─▶ RFQ agent
                                │
                                ├─ read:   gpt-6-luna, one small call (numbers + units only, reasoning off)
                                │          └─ free code checks: units, density (kg/m³), every number must be in
                                │             the mail, ready date, airport codes, a total counted twice
                                │             └─ fails? → gpt-6.1-terra reads it again → still impossible? → a person
                                ├─ traps:  dangerous goods in attachments (xlsx, PDF, file names), packing-list totals,
                                │          missing pickup address → one short question, the answer resumes the RFQ
                                ├─ carriers: every airline serving the lane + truckers of the pickup zone, in parallel;
                                │          per-kg / surcharge bids → one all-in total; questions answered in-thread
                                ├─ price:  backend (rate sheets + 5U portal + bids), cheapest / fastest / 50-50
                                ├─ gate:   last free check (one amount, DG papers, deadline, special cargo); a held
                                │          quote goes out by itself at 4:00 (an answer always beats none)
                                └─ quote:  hand-written templates in 8 languages, the customer's first name, one amount
customer "yes" ─▶ booking agent ─▶ portal booking by rate ID (or by email to the airline), exactly once
tracking@ question ─▶ tracking agent ─▶ answered from our CRM, also without a reference ($0)
```

Orchestrator and actors: the orchestrator is plain code, so its decisions cost nothing. A model only *reads*; every
number that reaches a customer comes from code. A cheap model reads every mail, and the stronger one only reads the
hard ones.

## Measured

| | |
|---|---|
| LLM cost per request | **$0.00012** (one luna call, ~600 tokens in / 125 out); carrier declines are free |
| Extraction eval | **25 / 25** real and adversarial mails read right (`evals/extract_eval.py`): lots, tonnes, cubic feet, German "1.233 kg", per-piece volumes, French/Spanish, corrections. Before the code checks: 21 / 25, with 3 priced wrong |
| Cheaper model? | gpt-5-nano: 35 % cheaper, but 5 / 25 wrong, so not used. Precision first: the mails get harder every hour |
| Next-trap scenarios | 51 likely next twists run through the real code (`test_next_traps.py`): 33 handled, 18 known gaps marked |
| Answer time | ~40 s on normal rounds (full time points until 2:00) |
| Tests | `uv run pytest -q`: 335 pass |

## Where to look

| File | What it does |
|---|---|
| `main.py` | worker loop: poll, route, one thread per mail; resumes half-priced RFQs after a restart |
| `extract.py` | the one LLM call, units by code, free plausibility checks, escalation |
| `rfq_agent.py` | carrier round, pricing, gate, quote, fallback quote, the missing-pickup question |
| `bids.py` | carrier replies → one all-in total (regex first, LLM only for shapes code can't price) |
| `dg.py`, `attachments.py` | dangerous goods and totals from packing lists (xlsx, PDF, docx, csv) |
| `gate.py` | the last check before a quote leaves |
| `booking_agent.py`, `tracking_agent.py`, `tracking_match.py` | yes/no/questions, booking once, tracking answers |
| `templates.py`, `quote_style.py` | the mails customers and carriers read |
| `evals/` | the extraction eval: `--replay` re-checks code changes for $0 |

Run: see `AGENTS.md`. Never run a live worker next to the one on the live machine: every mail would be answered twice.
