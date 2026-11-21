# agent/AGENTS.md
<!-- Folder-specific rules. Root AGENTS.md and AI_GUIDELINES.md always apply. Keep short. -->
Owner: Julien. Don't edit files outside this folder without asking.

## Commands (run from `agent/`)
- Run: worker comes with A3
- Test: `uv run pytest -q` · single test: `uv run pytest -q test_agent_core.py::test_route`

## Files
- `llm.py`: the only gateway caller. `chat_json()` returns (data, cost_usd) and logs every call.
- `inbox.py`: mailbox adapters (`fetch` / `reply` / `send`). `FixtureMailbox` reads JSON mails from a folder until the 5U mailbox API is known.
- `router.py`: rules-first `route(mail, carriers, known_thread)`. No LLM.

## Rules
- Every LLM call goes through `llm.chat_json`. A new model needs its price in `llm.PRICES`.
- Budget: one tiny gateway call per RFQ (no call = no cost points; big calls eat the 40 cost points).
- Data shapes sent to the backend must match docs/CONTRACT.md (proposal: docs/PLAN.md §7).
- Never send a customer anything before the quote: the first reply in a thread is the one that counts.
