# watch/AGENTS.md
Owner: Ulas. Monitoring tools that only READ 5U's APIs. Root AGENTS.md and AI_GUIDELINES.md apply.

- `board_watch.py`: polls /v1/board/me + /v1/board every 30 s (5U's refresh rate), prints alerts, optional phone push (`NTFY_TOPIC`).
- Test mode only for now: not wired into the agent or backend. Don't import it from `agent/` or `backend/` yet.
- Test: `cd watch && ../agent/.venv/Scripts/python -m pytest -q` (or any Python 3.12+ with pytest; stdlib only, no packages).
- Demo on sample data: `python board_watch.py --me fixtures/me.json --board fixtures/board.json --once`
