"""Board watcher (U5): reads 5U's leaderboard every 15 s and alerts on our missed or rejected requests. Read-only.

Public mode (no key): from /v1/board alone it sees, per round, whether we answered and got accepted (our counters),
how many points we got (our total), and which airline the other teams booked (= where the best price was).
Key mode (FIVEU_API_KEY or --me): adds /v1/board/me reason codes and the best price behind our accuracy points.
Alerts print, and go to a phone via ntfy.sh when NTFY_TOPIC is set. Not connected to the agent or backend.

Run:  python board_watch.py                       live, public mode (add the key for key mode)
      python board_watch.py --report              one-off: field vs us for every round on the board now
      python board_watch.py --board fixtures/board_real.json --report
"""
import argparse
import json
import os
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai")
TEAM = os.environ.get("TEAM_NAME", "leylu")
# The board's data is live (new bookings showed up 0-16 s after booked_at at 15 s polling); the page's 30 s is
# only its own timer. 15 s = ~8 s average delay for one ~10 KB request.
POLL_S = float(os.environ.get("POLL_SECONDS", "15"))
HEARTBEAT_S = 1800  # silent "Watcher alive" push every 30 min
BAD = {"rejected", "no answer", "voided"}
ACCURACY_MAX, ACCEPT_BAND, TIME_MAX = 45, 0.05, 15
# 1:30 leaves a person 4.5 min to step in. The agent's carrier cut-off is also 90 s, so a slow carrier can trigger
# it for a round that then goes fine: an "answered after all" push follows.
NO_ANSWER_ALERT_S = float(os.environ.get("NO_ANSWER_ALERT_SECONDS", "90"))


def get(path: str, key: str | None = None) -> dict:
    req = urllib.request.Request(BASE + path, headers={"X-API-Key": key} if key else {})
    with urllib.request.urlopen(req, timeout=8) as r:  # a hung request must not hold up the next poll
        return json.load(r)


def ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def mmss(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


# ---- public mode -------------------------------------------------------------------------------------------

def field_vs_us(board: dict, rnd: dict) -> tuple[str | None, int, str | None]:
    """(airline most other teams booked in this round, how many teams, the airline we booked or None).

    shortcut: bookings carry no round, so a booking belongs to the round whose window [sent, expiry + 30 s] holds it;
    a team booking an old round late can land in the wrong round (majority keeps it right). Upgrade: key mode.
    """
    me = next(t["team"] for t in board["ranking"] if t["name"] == TEAM)
    start, end = ts(rnd["sent_at"]), ts(rnd["expires_at"]) + 30
    books = {(b["team"], b["airline"]) for b in board.get("bookings", []) if start <= ts(b["booked_at"]) <= end}
    others = Counter(airline for team, airline in books if team != me)
    ours = next((airline for team, airline in books if team == me), None)
    top, n = others.most_common(1)[0] if others else (None, 0)
    return top, n, ours


def report(board: dict) -> list[str]:
    lines = []
    for rnd in sorted(board.get("rounds", []), key=lambda r: r["round_no"]):
        top, n, ours = field_vs_us(board, rnd)
        field = f"field booked {top} ({n} teams)" if top else "nobody booked"
        lines.append(f"Round {rnd['round_no']} ({rnd['status']}, {rnd['accepted']}/{rnd['answered']} teams accepted): "
                     f"{field}; we {'booked ' + ours if ours else 'did not book (not accepted or no answer)'}")
    return lines


def accuracy_gap(points: float, answered_s: float) -> float | None:
    """How far above the best price we were, from our points on an accepted round. Assumes accuracy falls
    linearly from 45 at the best price to 0 at +5%; only when time points were surely full (answered by 2:00)."""
    if answered_s > 120:
        return None
    return ACCEPT_BAND * (1 - min(points - TIME_MAX, ACCURACY_MAX) / ACCURACY_MAX)


def check_public(state: dict, board: dict, now: float) -> list[tuple[bool, str]]:
    """(push?, text) for what changed since the last poll. Our counters move within ~30 s of a verdict."""
    us = next(t for t in board["ranking"] if t["name"] == TEAM)
    rounds = sorted((r for r in board.get("rounds", []) if not r["voided"]), key=lambda r: r["round_no"])
    last, state["us"] = state.get("us"), {k: us[k] for k in ("answered", "accepted", "total")}
    if last is None:  # first poll: baseline only, don't report the past (use --report for that)
        state["done"] = [r["round_no"] for r in rounds]
        return []
    out, rec = [], state.setdefault("rounds", {})
    d_ans, d_acc, d_tot = (us[k] - last[k] for k in ("answered", "accepted", "total"))
    live = next((r for r in rounds if r["status"] == "open" and r["round_no"] not in state["done"]), None)
    if live:
        n, r = live["round_no"], rec.setdefault(str(live["round_no"]), {})
        elapsed, alerted = now - ts(live["sent_at"]), r.setdefault("alerted", [])
        if d_ans > 0:
            r.setdefault("answered_s", elapsed)
            if "no answer" in alerted:
                out.append((True, f"Round {n}: answered at {mmss(elapsed)} after all"))
        if d_acc > 0:
            r["accepted"], r["points"] = True, round(d_tot, 2)
            if "not accepted" in alerted:
                out.append((True, f"Round {n}: accepted after all (+{d_tot:.2f})"))
        if "answered_s" not in r and elapsed > NO_ANSWER_ALERT_S and "no answer" not in alerted:
            alerted.append("no answer")
            out.append((True, f"Round {n}: no answer from us after {mmss(elapsed)} "
                              f"({live['answered']} teams answered): open the Sessions UI"))
        # 5U scores on arrival: in 23 answers watched, the verdict showed up in the same poll 22 times, never later
        if "answered_s" in r and not r.get("accepted") and "not accepted" not in alerted:
            alerted.append("not accepted")
            out.append((True, f"Round {n}: answered but NOT accepted "
                              f"({live['accepted']}/{live['answered']} teams accepted)"))
    if d_tot and not d_acc:
        out.append((False, f"Points posted outside a quote: {d_tot:+.2f} (hourly cost points or a bonus)"))
    for rnd in rounds:  # close a round 30 s after expiry, when its bookings are in
        n = rnd["round_no"]
        if n in state["done"] or now < ts(rnd["expires_at"]) + 30:
            continue
        state["done"].append(n)
        r = rec.get(str(n), {})
        top, k, ours = field_vs_us(board, rnd)
        field = f"field booked {top} ({k} teams)" if top else "nobody booked"
        if r.get("accepted"):
            gap = accuracy_gap(r["points"], r.get("answered_s", 999))
            sway = f", about {gap:.1%} above the best price" if gap else ""
            out.append((False, f"Round {n} accepted: +{r['points']:.2f} pts{sway}"))
            if ours and top and ours != top:
                out.append((True, f"Round {n}: we booked {ours}, most teams booked {top}"))
        elif "answered_s" in r:
            out.append((True, f"Round {n} not accepted: {field}, we booked {ours or 'nothing'}"))
        else:
            out.append((True, f"Round {n} closed with NO answer from us: {field}"))
    return out


# ---- key mode (needs FIVEU_API_KEY) ------------------------------------------------------------------------

def requests_of(me: dict) -> list[dict]:
    # shortcut: /v1/board/me has no schema; names follow the public board (round_no) with fallbacks. Check live.
    items = next((v for k, v in me.items() if isinstance(v, list) and k != "bookings"), [])
    return [{
        "round": i.get("round_no") or i.get("round") or i.get("id"),
        "verdict": (i.get("verdict") or "").lower(),
        "reason": i.get("reason") or i.get("reason_code"),
        "points": i.get("points") or {},
        "price": i.get("price") or i.get("total_price"),
        "keys": sorted(i),
    } for i in items]


def best_price(our_price: float, accuracy: float) -> float:
    """True best price from our price and accuracy points, assuming points fall linearly from 45 at best to 0 at +5%."""
    return our_price / (1 + ACCEPT_BAND * (1 - accuracy / ACCURACY_MAX))


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
            rnd = next((x for x in board.get("rounds", []) if x.get("round_no") == r["round"]), {})
            others = rnd.get("accepted", 0)
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


# ---- loop --------------------------------------------------------------------------------------------------

URGENT = ("no answer from us", "NOT accepted", "not accepted:", "closed with NO answer")


def priority_of(text: str) -> tuple[str, str]:
    """ntfy (priority, tag): 5 breaks through do-not-disturb, 1 is a silent heartbeat."""
    if text.startswith("Watcher alive"):
        return "1", "heartbeat"
    if any(s in text for s in URGENT):
        return "5", "rotating_light"
    if "after all" in text or "back online" in text:
        return "3", "white_check_mark"
    return "4", "warning"


def notify(text: str, push: bool = True) -> None:
    print(time.strftime("%H:%M:%S"), text, flush=True)
    if push and (topic := os.environ.get("NTFY_TOPIC")):  # phone push via ntfy.sh, only when a topic is set
        priority, tag = priority_of(text)
        headers = {"Title": "Leylu board watcher", "Priority": priority, "Tags": tag}
        try:  # offline laptop: the push fails too, and that must never stop the watcher
            req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=text.encode(), headers=headers)
            urllib.request.urlopen(req, timeout=8)
        except Exception as e:
            print(time.strftime("%H:%M:%S"), f"push failed: {e}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--me"), ap.add_argument("--board")
    ap.add_argument("--once", action="store_true"), ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))  # noqa: E731
    if args.report:
        print("\n".join(report(read(args.board) if args.board else get("/v1/board"))))
        return
    state_file = Path(os.environ.get("WATCH_STATE", ".watch_state.json"))
    state = json.loads(state_file.read_text()) if state_file.exists() else {"seen": [], "reasons": [], "streak": 0}
    key, failures, offline_since, last_beat = os.environ.get("FIVEU_API_KEY"), 0, "", 0.0
    while True:
        started = time.time()
        try:
            board = read(args.board) if args.board else get("/v1/board")
            if failures:  # each poll reads the full board, so nothing that happened meanwhile is lost
                notify(f"Board watcher back online (offline since {offline_since}, {failures} failed polls)")
            failures = 0
            if started - last_beat > HEARTBEAT_S:  # so a reader can tell "all quiet" from "watcher dead"
                last_beat, us = started, next(t for t in board["ranking"] if t["name"] == TEAM)
                notify(f"Watcher alive: rank {us['rank']}, {us['total']:.2f} pts, "
                       f"{us['accepted']}/{us['answered']} accepted")
            for push, text in check_public(state, board, time.time()):
                notify(text, push)
            if args.me or key:
                for text in check(state, read(args.me) if args.me else get("/v1/board/me", key), board):
                    notify(text)
            state_file.write_text(json.dumps(state))
        except Exception as e:  # keep watching through network blips
            failures += 1
            if failures == 1:  # tell right away, once per outage, so silence never looks like "all fine"
                offline_since = time.strftime("%H:%M:%S")
                notify(f"Board watcher can't reach 5U: {e}")
            else:
                print(time.strftime("%H:%M:%S"), f"poll failed ({failures}): {e}", flush=True)
        if args.once:
            break
        time.sleep(max(0.0, POLL_S - (time.time() - started)))  # fixed rhythm: a slow request doesn't add drift


if __name__ == "__main__":
    main()
