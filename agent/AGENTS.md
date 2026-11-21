# agent/AGENTS.md
<!-- Folder-specific rules. Root AGENTS.md and AI_GUIDELINES.md always apply. Keep short. -->
Owner: Julien. Don't edit files outside this folder without asking.

## Commands (run from `agent/`)
- Run live: `uv run --env-file ../.env python main.py` (needs `FIVEU_API_KEY` from the kit card and the backend on `BACKEND_URL`, default http://localhost:8000)
- Run local: `MOCK=1 uv run --env-file ../.env python main.py` (mails from `fixtures/inbox/`, nothing is sent; the LLM still needs the key from `.env`; sessions go to `BACKEND_URL`, so use a local backend, not the live one)
- Setup once: fill in `FIVEU_API_KEY` and `GATEWAY_OPENAI_KEY` in the root `.env`, then `uv run --env-file ../.env python setup_5u.py` (checks the team key, stores the OpenAI key in the gateway, lists allowed models, shows the raw mail fields)
- Test: `uv run pytest -q` · single test: `uv run pytest -q test_agent_core.py::test_route`

## Files
- `setup_5u.py`: one-time setup + health check for the 5U APIs.
- `main.py`: worker loop: fetch → route → RFQ / reply / tracking each in their own thread. A mail whose dispatch fails (e.g. backend down for a moment) is retried every poll for up to 5 minutes. Live mode: only one worker per machine (file lock in the temp dir, `WORKER_LOCK_FILE`), and RFQs older than 6 minutes are skipped (they can't score; protects a fresh `.since_id` from answering the backlog). On start (live) it resumes RFQs that were being priced when it stopped (`resume_unfinished`: stage new/pricing, no quote, ≥ 30 s of the 6 minutes left; the mail is fetched again by id).
- `llm.py`: the only gateway caller (5U gateway `/v1/gateway`, team key). `chat_json()` returns (data, cost_usd) and logs every call.
- `inbox.py`: mailbox adapters (`fetch` / `reply` / `send` / `attachment`). `FiveUMailbox` = the live 5U mailbox (thread = first mail's id, `in_reply_to` for replies, last seen id kept in `.since_id`); `FixtureMailbox` for tests and local runs.
- `router.py`: rules-first `route(mail, carriers, known_thread)`. No LLM.
- `airports.py`: codes we can price (kit carrier list, sheets, portal ports, zones); `priceable()` turns another airport or city code of a city we serve into ours (HND → NRT, EWR → JFK, "Tokyo" → NRT), never changes a priced code. `AIRPORT_ALIASES=off` disables it.
- `extract.py`: the one LLM call per RFQ (copies numbers + units); `to_rfq()` converts to cm/kg in code and lists what's missing.
- `rfq_agent.py`: extract → mail carriers → collect bids until the cut-off (`BID_CUTOFF_SECONDS`, default 90 s after the RFQ) → `POST /api/price` with the bids → quote in the customer's thread → session events.
- `booking_agent.py`: customer reply → accept / decline / question (rules; LLM only if unclear or a question) → `POST /api/book` → booking mail in the thread. Also handles the airline's "Booking BK-… confirmed" mail.
- `tracking_agent.py`: `tracking@` questions → find the booking by reference → answer from the CRM (no LLM).
- `bids.py`: `parse_bid` (regex, free) → `read_bid` (LLM only if the regex fails); `BidBoard` hands carrier replies to the waiting RFQ thread.
- `carriers.py`: carrier list (`CARRIERS_FILE`, default `fixtures/carriers.json`, our own format until the start-kit list arrives) and who to ask per RFQ.
- `templates.py`: customer quote (one all-in amount) and carrier bid request (asks for a reply format the regex reads). Placeholder wording until U4.
- `backend.py`: HTTP client for the backend contract.
- `gate.py`: quote gate, the last free check before every quote (rules, no LLM): special cargo (DG beyond dg.py, temperature, perishable, valuables, oversize, live animals), arrival deadline and budget next to the ask, door-to-port without a pickup leg, a total far below the others, other currency, prompt injection, one amount per mail. fix = we change the quote, hold = flag + ntfy, auto-send at `GATE_AUTO_SEND_SECONDS` (240) unless a person pauses or quotes. `GATE_MODE=enforce|warn|off`.
- `amendments.py`: customer mails that arrive in the thread before our quote; the RFQ agent reads the request again with them before quoting.
- `postmortem.py <session> [--mail <5U id>]`: runs the gate on a sent quote (no LLM, sends nothing) to find the missing rule after a reject.
- `evals/traps.json` + `test_traps.py`: every rejected live round and expected trap through the whole RFQ pipeline. A new reject → add a case first.

## Rules
- Every LLM call goes through `llm.chat_json`. A new model needs its price in `llm.PRICES`.
- Budget: one tiny gateway call per RFQ (no call = no cost points; big calls eat the 40 cost points).
- Data shapes sent to the backend must match docs/CONTRACT.md (proposal: docs/PLAN.md §7).
- Never send a customer anything before the quote: the first reply in a thread is the one that counts.
