# watch/AGENTS.md
Owner: Ulas. Monitoring tools that only READ 5U's APIs. Root AGENTS.md and AI_GUIDELINES.md apply.

- `board_watch.py`: polls 5U's board every 30 s (5U's refresh rate) and alerts on our missed / rejected requests.
  - Public mode, no key: our answered/accepted/points per round + which airline the other teams booked.
  - Key mode (`FIVEU_API_KEY` set): adds `/v1/board/me` reason codes and the best price behind our accuracy points.
  - Phone push via ntfy.sh when `NTFY_TOPIC` is set (problems only; info lines just print).
- Standalone: not wired into the agent or backend. Don't import it from `agent/` or `backend/`. It sends no mail, makes no LLM or portal calls.
- Run: `python board_watch.py` (any machine, Python 3.11+, stdlib only) · one-off history: `python board_watch.py --report`
- Test: `cd watch && ../agent/.venv/bin/python -m pytest -q` (Windows: `..\agent\.venv\Scripts\python`)
