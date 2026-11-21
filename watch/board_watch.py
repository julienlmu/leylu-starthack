"""Board watcher (U5): reads 5U's leaderboard every 30 s and turns each scored request into an alert. Read-only.

Not connected to the agent or backend yet: it only reads /v1/board/me + /v1/board and prints (and optionally
pushes to a phone via ntfy.sh when NTFY_TOPIC is set). Test mode: --me / --board point at local JSON files.

Run:  uv run --env-file ../.env python board_watch.py            (live, needs FIVEU_API_KEY)
      uv run python board_watch.py --me fixtures/me.json --board fixtures/board.json --once
"""
import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

BASE = os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai")
TEAM = os.environ.get("TEAM_NAME", "leylu")
BAD = {"rejected", "no answer", "voided"}
ACCURACY_MAX, ACCEPT_BAND = 45, 0.05


def get(path: str, key: str | None = None) -> dict:
    req = urllib.request.Request(BASE + path, headers={"X-API-Key": key} if key else {})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def requests_of(me: dict) -> list[dict]:
    # shortcut: field names guessed from the API prose (no schema until the first round); fix here once seen live.
    items = next((v for k, v in me.items() if isinstance(v, list) and k != "bookings"), [])
    return [{
        "round": i.get("round") or i.get("round_id") or i.get("id"),
        "verdict": (i.get("verdict") or "").lower(),
        "reason": i.get("reason") or i.get("reason_code"),
        "points": i.get("points") or {},
        "price": i.get("price") or i.get("total_price"),
        "keys": sorted(i),
    } for i in items]


def best_price(our_price: float, accuracy: float) -> float:
    """True best price from our price and accuracy points, assuming points fall linearly from 45 at best to 0 at +5%."""
    over = ACCEPT_BAND * (1 - accuracy / ACCURACY_MAX)
    return our_price / (1 + over)


def others_accepted(board: dict, round_id) -> int:
    # shortcut: public round fields guessed as well ("round"/"id", "accepted" count); check on the first live round.
    rnd = next((r for r in board.get("rounds", []) if r.get("round") == round_id or r.get("id") == round_id), {})
    return rnd.get("accepted", 0) if isinstance(rnd.get("accepted"), int) else 0


def check(state: dict, me: dict, board: dict) -> list[str]:
    """Alerts for requests scored since the last check. `state` remembers seen rounds and reason codes."""
    alerts = []
    for r in reversed(requests_of(me)):  # API lists newest first; walk oldest first
        if r["round"] is None or not r["verdict"]:  # field names differ from the guess: say so once, don't go quiet
            if not state.get("warned"):
                state["warned"] = True
                alerts.append(f"board/me fields not recognised ({', '.join(r['keys'])}): fix requests_of()")
            continue
        if r["verdict"] in ("open", "pending") or r["round"] in state["seen"]:
            continue
        state["seen"].append(r["round"])
        state["streak"] = state["streak"] + 1 if r["verdict"] in BAD else 0
        if r["reason"] and r["reason"] not in state["reasons"]:
            state["reasons"].append(r["reason"])
            alerts.append(f"First time we see reason code '{r['reason']}' (round {r['round']}): "
                          f"if it's new after the first hour, something changed")
        if r["verdict"] in BAD:
            others = others_accepted(board, r["round"])
            hint = f", {others} other team(s) got it accepted: a better price existed" if others else ""
            alerts.append(f"Round {r['round']} {r['verdict']} ({r['reason'] or 'no reason'}){hint}")
        elif r["verdict"] == "accepted" and r["price"] and "accuracy" in r["points"]:
            acc = r["points"]["accuracy"]
            if acc < ACCURACY_MAX:
                best = best_price(r["price"], acc)
                alerts.append(f"Round {r['round']} accepted, {acc:g}/45 accuracy: best ~{best:,.2f}, "
                              f"we were {r['price'] / best - 1:.1%} high")
        if state["streak"] == 2:
            alerts.append("Two failed requests in a row: check the Sessions UI now")
    return alerts


def notify(text: str) -> None:
    print(time.strftime("%H:%M:%S"), text, flush=True)
    if topic := os.environ.get("NTFY_TOPIC"):  # phone push via ntfy.sh, only when a topic is set
        urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", data=text.encode()), timeout=10)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--me"), ap.add_argument("--board"), ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    state_file = Path(os.environ.get("WATCH_STATE", ".watch_state.json"))
    state = json.loads(state_file.read_text()) if state_file.exists() else {"seen": [], "reasons": [], "streak": 0}
    key = os.environ.get("FIVEU_API_KEY")
    while True:
        try:
            me = json.loads(Path(args.me).read_text()) if args.me else get("/v1/board/me", key)
            board = json.loads(Path(args.board).read_text()) if args.board else get("/v1/board")
            for a in check(state, me, board):
                notify(a)
            state_file.write_text(json.dumps(state))
        except Exception as e:  # keep watching through network blips
            notify(f"board watcher error: {e}")
        if args.once:
            break
        time.sleep(30)  # 5U refreshes the board every 30 s


if __name__ == "__main__":
    main()
