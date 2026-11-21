# agent/AGENTS.md
<!-- Folder-specific rules. Root AGENTS.md and AI_GUIDELINES.md always apply. Keep short. -->
Owner: Julien. Don't edit files outside this folder without asking.

## Commands (run from `agent/`)
- Run: `uv run python main.py` (needs the backend on `BACKEND_URL`, default http://localhost:8000; reads mails from `fixtures/inbox/` until the 5U mailbox adapter exists)
- Test: `uv run pytest -q` · single test: `uv run pytest -q test_agent_core.py::test_route`

## Files
- `main.py`: worker loop: fetch → route → RFQ / reply / tracking each in their own thread.
- `llm.py`: the only gateway caller. `chat_json()` returns (data, cost_usd) and logs every call.
- `inbox.py`: mailbox adapters (`fetch` / `reply` / `send`). `FixtureMailbox` reads JSON mails from a folder until the 5U mailbox API is known.
- `router.py`: rules-first `route(mail, carriers, known_thread)`. No LLM.
- `extract.py`: the one LLM call per RFQ (copies numbers + units); `to_rfq()` converts to cm/kg in code and lists what's missing.
- `rfq_agent.py`: extract → mail carriers → collect bids until the cut-off (`BID_CUTOFF_SECONDS`, default 90 s after the RFQ) → `POST /api/price` with the bids → quote in the customer's thread → session events.
- `booking_agent.py`: customer reply → accept / decline / question (rules; LLM only if unclear or a question) → `POST /api/book` → booking mail in the thread. Also handles the airline's "Booking BK-… confirmed" mail.
- `tracking_agent.py`: `tracking@` questions → find the booking by reference → answer from the CRM (no LLM).
- `bids.py`: `parse_bid` (regex, free) → `read_bid` (LLM only if the regex fails); `BidBoard` hands carrier replies to the waiting RFQ thread.
- `carriers.py`: carrier list (`CARRIERS_FILE`, default `fixtures/carriers.json`, our own format until the start-kit list arrives) and who to ask per RFQ.
- `templates.py`: customer quote (one all-in amount) and carrier bid request (asks for a reply format the regex reads). Placeholder wording until U4.
- `backend.py`: HTTP client for the backend contract.

## Rules
- Every LLM call goes through `llm.chat_json`. A new model needs its price in `llm.PRICES`.
- Budget: one tiny gateway call per RFQ (no call = no cost points; big calls eat the 40 cost points).
- Data shapes sent to the backend must match docs/CONTRACT.md (proposal: docs/PLAN.md §7).
- Never send a customer anything before the quote: the first reply in a thread is the one that counts.
