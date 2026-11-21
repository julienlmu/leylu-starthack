# backend/AGENTS.md
<!-- Folder-specific rules. Root AGENTS.md and AI_GUIDELINES.md always apply. Keep short. -->
Owner: Orhun. Don't edit files outside this folder without asking.

## Commands (run from `backend/`)
- Run: `uv run --env-file ../.env uvicorn app:app --reload --port 8000` (or `make backend` from the root)
- Test: `uv run pytest -q` · single test: `uv run pytest -q test_app.py::test_find_by_thread_and_reference`
- DB: SQLite file `crm.sqlite3` next to `app.py` (`DB_PATH` to change it; gitignored). Delete it to start empty.

## Files
- `app.py`: FastAPI app and routes (`create_app(crm, mailbox)` so tests inject an in-memory DB and a fake mailbox).
- `crm.py`: sessions + events in SQLite. JSON fields (`rfq`, `bids`, `quote`, `booking`, `status_updates`) are stored as text; PATCH replaces whole fields.
- `stream.py`: SSE fan-out for `GET /api/stream` (`data: <Event>` per event, `: ping` every 15 s).
- `mailbox.py`: the only mail the backend sends: a person's reply from the Sessions UI (intervene `send`).
- `pricing.py`: `/api/price`. Sheet math (chargeable kg, minimum before surcharges, next-break check), portal and bid options, door-to-port, cheapest/fastest/balanced choice. Worked examples in `test_pricing.py` come from docs/KIT_SUMMARY.md §6.
- `portal.py`: 5U portal client (ports, brackets, rates with cache and the 10-per-minute budget, booking).
- `tariffs.py`: rate sheets (`data/tariffs.json` = all 10 start-kit sheets, normalized; ingested tariffs go to `data/ingested/`) and pickup zones (`data/pickup_zones.csv`).

## Rules
- Data shapes must match `docs/CONTRACT.md` exactly. The agent (`agent/backend.py`) and the frontend (`frontend/lib/types.ts`) read them.
- Endpoints that publish to the stream are `async def` (the broadcaster's queues live on the event loop).
- No LLM calls in the backend: pricing, ingestion and booking are code.
- Portal rate calls are scarce (10 per minute per team): go through `Portal.rate` (cache + budget), mark nice-to-have calls `optional=True`.
