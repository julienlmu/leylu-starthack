# watch/AGENTS.md
Owner: Ulas. Monitoring tools that only READ 5U's APIs. Root AGENTS.md and AI_GUIDELINES.md apply.

- `board_watch.py`: polls 5U's board every 30 s (5U's refresh rate) and alerts on our missed / rejected requests.
  - Public mode, no key: our answered/accepted/points per round + which airline the other teams booked.
  - Key mode (`FIVEU_API_KEY` set): adds `/v1/board/me` reason codes and booking checks: `booked: false` or not booked
    (= no tracking question, no +10), and a booked round without its +10 after 14 min.
  - Points per round are read with 5U's scoring (docstring of `board_watch.py`): accuracy 45 x (1 - |dev|/10 %),
    time 15 until 2:00 then linear to 0 at 6:00; hourly cost points are divided by that hour's accepted quotes.
  - Phone push via ntfy.sh when `NTFY_TOPIC` is set (problems only; info lines just print).
- Standalone: not wired into the agent or backend. Don't import it from `agent/` or `backend/`. It sends no mail, makes no LLM or portal calls.
- Run: `python board_watch.py` (any machine, Python 3.11+, stdlib only) · one-off history: `python board_watch.py --report`
- Test: `cd watch && ../agent/.venv/bin/python -m pytest -q` (Windows: `..\agent\.venv\Scripts\python`)
