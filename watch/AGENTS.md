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
- Run: `uv run --no-project --python 3.12 python board_watch.py` (any machine, stdlib only) · one-off history: `python board_watch.py --report`
- Test: `cd watch && ../agent/.venv/bin/python -m pytest -q` (Windows: `..\agent\.venv\Scripts\python`)

## board_watch_live.py (the copy running during the event)
- The watcher that ran on Ulas's laptop during the challenge: polls every 15 s, pushes to ntfy topic `leylu-watch-31`
  (subscribe at https://ntfy.sh/leylu-watch-31), writes new reason codes to `docs/EMERGENCY_FIXES.md` via an
  `ulas/emergency-fixes` clone (`EF_REPO`), a 30-min heartbeat with rank and gap to the neighbours.
- Pushes only what needs a person (penalties, 0-point or rejected rounds, missed answers, humanity bonuses, new reason
  codes, outages, heartbeat); routine lines stay in the console. ntfy.sh allows 250 messages/day per IP: on HTTP 429 it
  waits the `Retry-After` ntfy sends and then pushes the held alerts as one bundle.
- Run on Windows: double-click `START_WATCHER.bat` (needs `FIVEU_API_KEY` in the environment or one line in
  `watch/team_key.txt`, gitignored). Elsewhere: `FIVEU_API_KEY=… NTFY_TOPIC=leylu-watch-31 uv run --no-project --python 3.12
  python board_watch_live.py` (never the system Python: 3.8 can't run `str | None`). Only ONE watcher at a time, and
  it never starts an agent.
- The ntfy topic is public: pushes carry board numbers, rounds and reason codes only. Customer text (sender, subject,
  sentences; only with `MAIL_READS=1`) stays in the console and the incident log.
- `board_watch.py` above is the tested base (with the booking checks); the live copy grew from it during the night.
