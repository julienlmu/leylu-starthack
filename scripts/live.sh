#!/usr/bin/env bash
# Runs the forwarder all night on ONE machine: backend (:8000), agent (live 5U mailbox) and the Sessions UI (:3000).
# Each process is restarted 3 s after it exits; logs go to logs/<name>.log; macOS is kept awake while it runs.
#
#   make live          start (Ctrl-C stops everything)
#   tail -f logs/*.log watch
#
# Never run this on two machines at once: two agents on one mailbox answer every mail twice.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs

LOCK=logs/live.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "live.sh: already running here (pid $(cat "$LOCK/pid" 2>/dev/null)). Stop it first or remove $LOCK." >&2
  exit 1
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"; kill 0' INT TERM EXIT

if [ ! -f .env ] || ! grep -q '^FIVEU_API_KEY=.' .env; then
  echo "live.sh: FIVEU_API_KEY missing in .env (kit card)" >&2
  exit 1
fi
PORT=$(grep -E '^PORT=' .env | tail -1 | cut -d= -f2); PORT=${PORT:-8000}

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
keep_running() {  # keep_running <name> <command…>
  local name=$1; shift
  while true; do
    echo "$(stamp) live.sh: start $name" >> "logs/$name.log"
    "$@" >> "logs/$name.log" 2>&1
    echo "$(stamp) live.sh: $name exited ($?), restart in 3 s" >> "logs/$name.log"
    sleep 3
  done
}

keep_running backend bash -c "cd backend && exec uv run --env-file ../.env uvicorn app:app --host 127.0.0.1 --timeout-graceful-shutdown 1 --port $PORT" &
for _ in $(seq 1 30); do curl -sf "localhost:$PORT/health" >/dev/null && break; sleep 1; done
curl -sf "localhost:$PORT/health" >/dev/null || echo "live.sh: backend not healthy yet, see logs/backend.log" >&2

if [ "${LIVE_AGENT:-1}" = "1" ]; then  # LIVE_AGENT=0: backend + UI only (nothing is sent)
  keep_running agent bash -c "cd agent && BACKEND_URL=http://localhost:$PORT PYTHONUNBUFFERED=1 exec uv run --env-file ../.env python main.py" &
fi
if [ "${LIVE_FRONTEND:-1}" = "1" ]; then
  keep_running frontend bash -c "BACKEND_URL=http://localhost:$PORT exec pnpm --dir frontend dev" &
fi
command -v caffeinate >/dev/null && caffeinate -dimsu -w $$ &

echo "live: backend :$PORT, agent on the 5U mailbox, UI http://localhost:3000. Logs: logs/. Ctrl-C stops all."
wait
