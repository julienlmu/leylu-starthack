# agent/AGENTS.md
<!-- Folder-specific rules. Root AGENTS.md and AI_GUIDELINES.md always apply. Keep short. -->
Owner: Julien. Don't edit files outside this folder without asking.

## Commands (run from `agent/`)
- Run: `uv run python main.py` (needs the backend on `BACKEND_URL`, default http://localhost:8000; reads mails from `fixtures/inbox/` until the 5U mailbox adapter exists)
- Test: `uv run pytest -q` · single test: `uv run pytest -q test_agent_core.py::test_route`

## Files
- `main.py`: worker loop: fetch → route → one thread per RFQ.
- `llm.py`: the only gateway caller. `chat_json()` returns (data, cost_usd) and logs every call.
- `inbox.py`: mailbox adapters (`fetch` / `reply` / `send`). `FixtureMailbox` reads JSON mails from a folder until the 5U mailbox API is known.
- `router.py`: rules-first `route(mail, carriers, known_thread)`. No LLM.
- `extract.py`: the one LLM call per RFQ (copies numbers + units); `to_rfq()` converts to cm/kg in code and lists what's missing.
- `rfq_agent.py`: extract → `POST /api/price` → quote in the customer's thread → session events.
- `templates.py`: customer mails, one all-in amount per quote (placeholder wording until U4).
- `backend.py`: HTTP client for the backend contract.

## Rules
- Every LLM call goes through `llm.chat_json`. A new model needs its price in `llm.PRICES`.
- Budget: one tiny gateway call per RFQ (no call = no cost points; big calls eat the 40 cost points).
- Data shapes sent to the backend must match docs/CONTRACT.md (proposal: docs/PLAN.md §7).
- Never send a customer anything before the quote: the first reply in a thread is the one that counts.
