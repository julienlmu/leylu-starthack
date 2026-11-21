"""Board watcher (U5): reads 5U's leaderboard every 30 s and alerts on our missed or rejected requests. Read-only.

Public mode (no key): from /v1/board alone it sees, per round, whether we answered and got accepted (our counters),
how many points we got (our total), and which airline the other teams booked (= where the best price was).
Key mode (FIVEU_API_KEY or --me): adds /v1/board/me reason codes and booking checks (booked: false, not booked,
no +10 tracking bonus after a booking).
Alerts print, and go to a phone via ntfy.sh when NTFY_TOPIC is set. Not connected to the agent or backend.

5U's scoring, reverse-engineered from our board deltas (rounds 1-11, exact to the cent):
- accuracy = 45 x (1 - |dev| / 10 %), dev = (ours - best) / best; below the best costs points too; over 5 % = rejected
- time = 15 up to 2:00, then linear to 0 at 6:00
- tracking +10 about 11 min after a round, only if 5U counts our booking (booked weight below the real one: it doesn't)
- cost: posted ~6 min after each full hour, up to 40 per accepted quote of that hour

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
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai")
TEAM = os.environ.get("TEAM_NAME", "leylu")
BAD = {"rejected", "no answer", "voided"}
ACCURACY_MAX, ACCURACY_ZERO, TIME_MAX = 45, 0.10, 15  # accuracy reaches 0 at 10 % off (only <= 5 % is accepted)
TIME_FULL_S, TIME_ZERO_S = 120, 360
NO_ANSWER_ALERT_S = 150  # time points start dropping at 2:00; a person still has ~3 min to step in
GAP_ALERT = 0.005  # push when an accepted round was 0.5 % or more off the best price (~2.3 points)
TRACKING_DUE_S = 14 * 60  # 5U asks ~11 min after the round and the +10 posts when we answer
COST_ALERT = 39.5  # push when the hourly cost points per accepted quote fall below this


def get(path: str, key: str | None = None) -> dict:
    req = urllib.request.Request(BASE + path, headers={"X-API-Key": key} if key else {})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


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


def time_points(answered_s: float) -> float:
    """15 up to 2:00, then linear to 0 at 6:00 (round 7: answered at 2:18.8 → 13.83)."""
    late = min(max(answered_s - TIME_FULL_S, 0), TIME_ZERO_S - TIME_FULL_S)
    return TIME_MAX * (1 - late / (TIME_ZERO_S - TIME_FULL_S))


def accuracy_gap(points: float, answered_s: float) -> float:
    """How far off the best price we were (above or below), from our points on an accepted round:
    accuracy = 45 x (1 - |dev| / 10 %). Round 2: +49.14 at 0:45 → 2.4 %. answered_s is from our 30 s polls."""
    accuracy = min(points - time_points(answered_s), ACCURACY_MAX)
    return max(0.0, ACCURACY_ZERO * (1 - accuracy / ACCURACY_MAX))


def hour_of(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M")


def cost_line(state: dict, points: float, now: float) -> tuple[bool, str]:
    """Hourly cost points: divided by our accepted quotes of the last full hour (by round start)."""
    end = now // 3600 * 3600
    start = end - 3600
    n = sum(1 for r in state.get("rounds", {}).values() if r.get("accepted") and start <= ts(r.get("sent", "1970-01-01T00:00:00+00:00")) < end)
    if not n:
        return False, f"Points posted outside a quote: {points:+.2f} (hourly cost points or a bonus)"
    each = points / n
    return each < COST_ALERT, (f"Hourly cost points {points:+.2f} for {n} accepted quotes of {hour_of(start)}-{hour_of(end)} UTC"
                               f" = {each:.2f} each (max 40): {'look for extra gateway calls' if each < COST_ALERT else 'fine'}")


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
        r.setdefault("sent", live["sent_at"])
        elapsed = now - ts(live["sent_at"])
        if d_ans > 0:
            r.setdefault("answered_s", elapsed)
        if d_acc > 0:
            r["accepted"], r["points"] = True, round(d_tot, 2)
        if "answered_s" not in r and elapsed > NO_ANSWER_ALERT_S and not r.get("warned"):
            r["warned"] = True
            out.append((True, f"Round {n}: no answer from us after {elapsed / 60:.1f} min "
                              f"({live['answered']} teams answered): open the Sessions UI"))
        if "answered_s" in r and not r.get("accepted") and elapsed - r["answered_s"] > 60 and not r.get("warned"):
            r["warned"] = True
            out.append((True, f"Round {n}: answered but not accepted after 60 s "
                              f"({live['accepted']}/{live['answered']} teams accepted)"))
    if d_tot and not d_acc:
        bonuses = round(d_tot / 10)
        if 1 <= bonuses <= 3 and abs(d_tot - 10 * bonuses) < 0.01:  # tracking answers (+10 each)
            state.setdefault("bonus_at", []).extend([now] * bonuses)
            out.append((False, f"Tracking bonus {d_tot:+.0f}"))
        else:
            out.append(cost_line(state, d_tot, now))
    for rnd in rounds:  # close a round 30 s after expiry, when its bookings are in
        n = rnd["round_no"]
        if n in state["done"] or now < ts(rnd["expires_at"]) + 30:
            continue
        state["done"].append(n)
        r = rec.get(str(n), {})
        top, k, ours = field_vs_us(board, rnd)
        field = f"field booked {top} ({k} teams)" if top else "nobody booked"
        if r.get("accepted"):
            gap = accuracy_gap(r["points"], r.get("answered_s", 0))
            sway = f", about {gap:.1%} off the best price (above or below)" if gap >= 0.0005 else ""
            out.append((gap >= GAP_ALERT, f"Round {n} accepted: +{r['points']:.2f} pts{sway}"))
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
        "booked": i.get("booked"),
        "sent_at": i.get("sent_at"),
        "keys": sorted(i),
    } for i in items]


def best_price(our_price: float, accuracy: float) -> float:
    """Best price from our price and accuracy points if we were above it (45 at best, 0 at +10 %)."""
    return our_price / (1 + ACCURACY_ZERO * (1 - accuracy / ACCURACY_MAX))


def check_bookings(state: dict, me: dict, now: float) -> list[str]:
    """Bookings that won't earn the +10 tracking bonus. /v1/board/me sets `booked` per accepted round: false once 5U
    rejects our booking (round 5/6: booked 1227.96 kg of a 1228 kg shipment), null when nothing was booked (round 7:
    a manual quote). A booked round with no +10 in the public total 8-14 min after its start: the answer failed."""
    out, done, bonus = [], state.setdefault("booking_checked", []), state.setdefault("bonus_at", [])
    rows = [r for r in reversed(requests_of(me)) if r["round"] is not None and r["sent_at"] and r["verdict"] == "accepted"]
    if not state.get("booking_baseline"):  # first run: don't alert on rounds that are already history
        state["booking_baseline"] = True
        done += [r["round"] for r in rows if now - ts(r["sent_at"]) > TRACKING_DUE_S]
    for r in rows:
        n, sent = r["round"], ts(r["sent_at"])
        if n in done:
            continue
        if r["booked"] is False:
            done.append(n)
            out.append(f"Round {n}: 5U doesn't count a booking for it (booked: false), so no tracking question and "
                       f"no +10. Booked weight below the real weight, a wrong rate, or nothing booked?")
        elif r["booked"] is None and now - sent > TIME_ZERO_S + 30:
            done.append(n)
            out.append(f"Round {n} accepted but not booked: no tracking +10 unless we book it (a manual quote?)")
        elif r["booked"] and now - sent > TRACKING_DUE_S:
            done.append(n)
            hit = next((t for t in bonus if sent + 8 * 60 <= t <= sent + TRACKING_DUE_S + 60), None)
            if hit is None:
                out.append(f"Round {n}: booked, but no +10 tracking bonus 14 min later: check the tracking answer")
            else:
                bonus.remove(hit)
    return out


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
            price = not r["reason"] or any(w in r["reason"].lower() for w in ("low", "high", "price"))
            hint = f", {others} other team(s) got it accepted" + (": a better price existed" if price else "") if others else ""
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

def notify(text: str, push: bool = True) -> None:
    print(time.strftime("%H:%M:%S"), text, flush=True)
    if push and (topic := os.environ.get("NTFY_TOPIC")):  # phone push via ntfy.sh, only when a topic is set
        urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", data=text.encode()), timeout=10)


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
    key = os.environ.get("FIVEU_API_KEY")
    while True:
        try:
            board = read(args.board) if args.board else get("/v1/board")
            for push, text in check_public(state, board, time.time()):
                notify(text, push)
            if args.me or key:
                me = read(args.me) if args.me else get("/v1/board/me", key)
                for text in check(state, me, board) + check_bookings(state, me, time.time()):
                    notify(text)
            state_file.write_text(json.dumps(state))
        except Exception as e:  # keep watching through network blips
            notify(f"board watcher error: {e}")
        if args.once:
            break
        time.sleep(30)  # 5U refreshes the board every 30 s


if __name__ == "__main__":
    main()
