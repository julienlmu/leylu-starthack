#!/usr/bin/env bash
# Deploys this working tree to a Linux server and (re)starts `make live` there in tmux (backend + live agent).
#
#   scripts/deploy.sh user@host [ssh-port] [ssh-key-file]
#   ssh -p PORT user@host -t tmux attach -t live      # watch it (detach: Ctrl-b d)
#   ssh -p PORT -N -L 8000:localhost:8000 user@host    # then `make frontend` here: the UI shows the server's data
#
# The code goes over SSH as a tar stream (no GitHub token on the server); .env is copied with scp.
# The server keeps its own CRM database and the agent's last seen mail id across deploys.
# Only one machine may run the live agent: stop any other `make live` / `make agent` first.
set -euo pipefail
TARGET=${1:?usage: scripts/deploy.sh user@host [ssh-port] [ssh-key-file]}
PORT=${2:-22}
KEY=${3:-}
DIR=${REMOTE_DIR:-leylu}
SSH=(ssh -p "$PORT" -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new)
SCP=(scp -P "$PORT" -o StrictHostKeyChecking=accept-new)
if [ -n "$KEY" ]; then SSH+=(-i "$KEY"); SCP+=(-i "$KEY"); fi
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "deploy: no .env here" >&2; exit 1; }

echo "deploy: copying code to $TARGET:$DIR"
COPYFILE_DISABLE=1 tar --exclude=./.git --exclude=node_modules --exclude=.venv --exclude=.next --exclude=./logs \
  --exclude='*.sqlite3*' --exclude=./kit --exclude=./agent/.since_id --exclude=./backend/data/ingested --exclude=.DS_Store --exclude=./.env \
  -czf - . | "${SSH[@]}" "$TARGET" "mkdir -p $DIR && tar -xzf - -C $DIR"
"${SCP[@]}" -q .env "$TARGET:$DIR/.env"

echo "deploy: setting up and starting on the server"
"${SSH[@]}" "$TARGET" "DIR=$DIR bash -s" <<'REMOTE'
set -euo pipefail
cd "$HOME/$DIR"
chmod 600 .env
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  python3 -m pip install --user --quiet uv 2>/dev/null || pip install --user --quiet uv
fi
echo "uv: $(uv --version)"
(cd backend && uv sync -q) && (cd agent && uv sync -q)
echo "5U API: $(curl -s -o /dev/null -w '%{http_code}' https://api.start-hack.5u.ai/health)"

if [ ! -f agent/.since_id ]; then
  # First deploy: skip the mails that arrived before the scored rounds (first RFQ Sat 16:00 Berlin = 15:00 UTC).
  (cd agent && uv run --env-file ../.env python - <<'PY'
import os, httpx
from datetime import datetime
START = datetime.fromisoformat("2026-11-21T15:00:00+00:00")
http = httpx.Client(base_url=os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai"),
                    headers={"X-API-Key": os.environ["FIVEU_API_KEY"]}, timeout=15)
since, last_old, seen = 0, 0, 0
while True:
    data = http.get("/v1/mailbox/messages", params={"since_id": since, "limit": 200}).json()
    for m in data["messages"]:
        seen += 1
        at = m.get("sent_at") or m.get("created_at") or m.get("received_at")
        try:
            old = datetime.fromisoformat(at.replace("Z", "+00:00")) < START
        except (AttributeError, ValueError):
            old = False
        if old:
            last_old = max(last_old, m["id"])
    if not data["messages"] or data["next_since_id"] == since:
        break
    since = data["next_since_id"]
open(".since_id", "w").write(str(last_old))
print(f"mailbox: {seen} mails so far, skipping ids <= {last_old} (before 16:00 Berlin)")
PY
  )
fi

if command -v tmux >/dev/null; then
  tmux kill-session -t live 2>/dev/null || true
  sleep 1; rm -rf logs/live.lock
  tmux new-session -d -s live "LIVE_FRONTEND=0 scripts/live.sh"
else
  pkill -f scripts/live.sh 2>/dev/null || true
  sleep 1; rm -rf logs/live.lock; mkdir -p logs
  LIVE_FRONTEND=0 nohup setsid scripts/live.sh > logs/live.out 2>&1 < /dev/null &
fi
for _ in $(seq 1 30); do curl -sf localhost:8000/health >/dev/null && break; sleep 1; done
echo "backend: $(curl -s localhost:8000/health)"
sleep 3; tail -3 logs/agent.log 2>/dev/null || true
REMOTE
echo "deploy: done. Watch: ssh -p $PORT $TARGET -t tmux attach -t live"
