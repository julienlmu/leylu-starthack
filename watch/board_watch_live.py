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
import io
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.error
import zipfile
import zlib
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


def get(path: str, key: str | None = None, raw: bool = False):
    req = urllib.request.Request(BASE + path, headers={"X-API-Key": key} if key else {})
    with urllib.request.urlopen(req, timeout=8) as r:  # a hung request must not hold up the next poll
        return r.read() if raw else json.load(r)


MAILBOX = {"since": 0, "mails": []}  # read-only copy of our inbox, fetched incrementally


def un_line(data: bytes) -> str | None:
    """First 'UN1234 …' text in an attachment (plain, xlsx/docx xml, or Flate PDF streams)."""
    texts = [data]
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            texts += [z.read(n) for n in z.namelist() if n.endswith(".xml")]
    for s in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            texts.append(zlib.decompress(s))
        except zlib.error:
            pass
    for t in texts:
        if m := re.search(rb"UN\s?\d{4}[^<)\r\n]{0,60}", t):
            return m.group().decode("latin-1").strip()
    return None


EF_REPO = os.environ.get("EF_REPO")  # a clone of branch ulas/emergency-fixes; unset = don't write incidents


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", EF_REPO, *args], capture_output=True, text=True, timeout=60)


def log_incident(r: dict, brief: str, board: dict) -> None:
    """Write the incident at the top of docs/EMERGENCY_FIXES.md and push it, for Orhun's Claude to turn into code."""
    if not EF_REPO:
        return
    try:
        rnd = next((x for x in board.get("rounds", []) if x.get("round_no") == r["round"]), {})
        took = mmss(ts(r["answered_at"]) - ts(r["sent_at"])) if r["answered_at"] else "never"
        top, k, _ = field_vs_us(board, rnd) if rnd else (None, 0, None)
        field = f"; field booked {top} ({k} teams)" if top else ""
        entry = (f"### AUTO · {time.strftime('%H:%M')} · round {r['round']} {r['verdict']} `{r['reason'] or '-'}`\n"
                 f"- Board: we answered at {took}; {rnd.get('accepted', '?')}/{rnd.get('answered', '?')} teams "
                 f"accepted{field}.\n"
                 f"- RFQ (round sent {r['sent_at'][11:19]} UTC): {brief}\n"
                 f"- For Orhun's Claude: find the session by received_at, run agent/postmortem.py on it, add the "
                 f"missing rule and a case in agent/evals/traps.json, test, deploy between rounds.\n\n")
        git("pull", "--rebase", "-q")
        path = Path(EF_REPO, "docs", "EMERGENCY_FIXES.md")
        text = re.sub(r"(## Incidents\r?\n\r?\n)", lambda m: m.group(1) + entry, path.read_text(encoding="utf-8"), 1)
        path.write_text(text, encoding="utf-8")
        git("commit", "-qam", f"docs: EMERGENCY_FIXES auto incident, round {r['round']} {r['reason'] or r['verdict']}")
        for _ in range(3):  # Codex may push to the same branch: rebase and retry
            if git("push", "-q").returncode == 0:
                print(time.strftime("%H:%M:%S"), f"incident for round {r['round']} pushed", flush=True)
                return
            git("pull", "--rebase", "-q")
        print(time.strftime("%H:%M:%S"), "incident push failed", flush=True)
    except Exception as e:
        print(time.strftime("%H:%M:%S"), f"incident log failed: {e}", flush=True)


# Signals from docs/POSSIBLE_TRAPS.md, checked on every new RFQ before we quote (heads-up, not a verdict)
TRAP_SIGNALS = [
    ("customer bans an airline", r"\b(do not|don't|never|not)\s+(offer|use|book|quote)\b"),
    ("customer requires an airline", r"\bonly\b.{0,40}\b(airline|carrier|with)\b|\bmust (be|fly) with\b|preferred carrier"),
    ("arrival deadline", r"\b(arrive|arrival|deliver\w*)\b.{0,20}\b(by|before|latest|no later than)\b|\bdeadline\b"),
    ("budget cap", r"\bbudget\b|\b(max(imum)?|not more than|up to)\s*(EUR|€|USD|\$)"),
    ("other currency asked", r"\b(in|quote in|price in)\s+(USD|CHF|GBP|dollars?|francs?|pounds?)\b"),
    ("door-to-door / incoterm", r"door[- ]to[- ]door|\b(DAP|DDP|EXW|FCA|CPT|CIP)\b|deliver to (the )?consignee"),
    ("dangerous goods words", r"\bUN\s?\d{4}\b|lithium|batter(y|ies)|aerosol|perfume|\bpaint\b|dry ice|flammable|corrosive|explosive|magnet"),
    ("temperature control", r"°\s?C\b|\bdegrees\b|refrigerat|frozen|cool chain|cold chain|\bpharma"),
    ("perishable / live / valuable", r"perishable|live animal|\bjewel|valuable|\bcash\b|human remains"),
    ("forwarded thread", r"^\s*(RE|FW|FWD|WG|AW|TR)\s*:|-----\s*Original Message|^\s*>"),
    ("prompt injection", r"ignore (all |the |any )?(previous|prior|above) instructions|you are (now|an ai)|system prompt|disregard"),
    ("two options asked", r"\btwo (quotes|options)\b|\boption [AB]\b|\bboth options\b"),
    ("oversize piece", r"\b([3-9]\d{2}|\d{4})\s*(cm|x)\b"),
]


def fetch_new_mail(key: str) -> None:
    """Only mails newer than the last one seen, at most 3 pages per call: 5U rate-limits the mailbox per team key,
    and the live agent polls the same mailbox (a 429 burst at 20:45 when reading from the start)."""
    for _ in range(1):  # 5U allows ONE mailbox poll per 5 s per team key (since ~20:45): every poll here takes one from the agent
        d = get(f"/v1/mailbox/messages?since_id={MAILBOX['since']}&limit=200", key)
        batch = d.get("messages", [])
        MAILBOX["mails"] = (MAILBOX["mails"] + batch)[-1500:]
        nxt = d.get("next_since_id")
        if not batch or nxt in (None, MAILBOX["since"]):
            return
        MAILBOX["since"] = nxt
        if len(batch) < 200:
            return


MAIL_READS = os.environ.get("MAIL_READS") == "1"  # off: since ~20:45 5U allows one mailbox poll per 5 s and the agent needs them


def find_rfq(key: str, sent_iso: str) -> dict | None:
    if not MAIL_READS:
        return None
    fetch_new_mail(key)
    t = ts(sent_iso)
    m = min((x for x in MAILBOX["mails"] if x.get("received_at")),
            key=lambda x: abs(ts(x["received_at"]) - t), default=None)
    return m if m and abs(ts(m["received_at"]) - t) <= 30 else None


def trap_signals(key: str, m: dict) -> list[str]:
    text = f"{m.get('subject') or ''}\n{m.get('body') or ''}"
    hits = [name for name, rx in TRAP_SIGNALS if re.search(rx, text, re.I | re.M)]
    for a in m.get("attachments") or []:
        if line := un_line(get(f"/v1/mailbox/messages/{m['id']}/attachments/{a['id']}", key, raw=True)):
            hits.append(f"{a.get('filename')} says {line}")
    return hits


def rfq_brief(key: str, sent_iso: str) -> str:
    try:
        if not (m := find_rfq(key, sent_iso)):
            return "mailbox not read (5U allows one poll per 5 s; the agent needs them)" if not MAIL_READS else "not found in the mailbox"
        parts = [f"'{m.get('subject')}' from {m.get('from')}"]
        # the customer's instructions (round 42: "Please do not offer Zephyr Steppe Cargo (ZS)") are usually the trap
        rules = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", m.get("body") or "")
                 if re.search(r"\b(do not|don't|not offer|avoid|exclud\w*|never|only|must|without|instead of)\b", s, re.I)]
        if rules:
            parts.append("customer says: " + " / ".join(r[:160] for r in rules[:3]))
        for a in m.get("attachments") or []:
            hit = un_line(get(f"/v1/mailbox/messages/{m['id']}/attachments/{a['id']}", key, raw=True))
            parts.append(f"{a.get('filename')}" + (f" says {hit}" if hit else " (no UN number)"))
        return "; ".join(parts)
    except Exception as e:
        return f"lookup failed: {e}"


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
            r["accepted"] = True
            if "not accepted" in alerted:
                out.append((True, f"Round {n}: accepted after all"))
        if "answered_s" not in r and elapsed > NO_ANSWER_ALERT_S and "no answer" not in alerted:
            alerted.append("no answer")
            out.append((True, f"Round {n}: no answer from us after {mmss(elapsed)} "
                              f"({live['answered']} teams answered): open the Sessions UI"))
        # 5U scores on arrival: in 23 answers watched, the verdict showed up in the same poll 22 times, never later
        if "answered_s" in r and not r.get("accepted") and "not accepted" not in alerted:
            alerted.append("not accepted")
            out.append((True, f"Round {n}: answered but NOT accepted "
                              f"({live['accepted']}/{live['answered']} teams accepted)"))
    # Since ~18:36 5U posts a round's points and its accepted count in different polls, so classify by size.
    pending = [x for x in rounds if x["round_no"] not in state["done"]]
    if d_tot:
        if round(d_tot, 2) == 10 and not d_acc:  # tracking bonus: log only
            out.append((False, f"Tracking bonus: {d_tot:+.2f}"))
        elif 0 < d_tot <= 60.5 and pending:  # a round is worth at most 60: these are the open/just-closed round's points
            r = rec.setdefault(str(pending[-1]["round_no"]), {})
            r["points"] = round(r.get("points", 0) + d_tot, 2)
        elif d_tot > 60.5:
            out.append((True, f"Cost points posted (hourly): {d_tot:+.2f}"))
        else:
            out.append((False, f"Board total changed by {d_tot:+.2f} (5U recalculation)"))
    for rnd in rounds:  # close a round 60 s after expiry, when its bookings and late points are in
        n = rnd["round_no"]
        if n in state["done"] or now < ts(rnd["expires_at"]) + 60:
            continue
        state["done"].append(n)
        r = rec.get(str(n), {})
        top, k, ours = field_vs_us(board, rnd)
        field = f"field booked {top} ({k} teams)" if top else "nobody booked"
        if r.get("accepted"):
            pts = r.get("points", 0)
            gap = accuracy_gap(pts, r.get("answered_s", 999)) if pts > 0 else None  # no points seen: no estimate
            sway = f", about {gap:.1%} above the best price" if gap else ""
            out.append((False, f"Round {n} accepted: +{pts:.2f} pts{sway}"))  # log only: key mode reports exact points
            if ours and top and ours != top:
                out.append((True, f"Round {n}: we booked {ours}, most teams booked {top}"))
        elif "answered_s" in r:
            out.append((True, f"Round {n} not accepted: {field}, we booked {ours or 'nothing'}"))
        else:
            out.append((True, f"Round {n} closed with NO answer from us: {field}"))
    return out


# ---- neighbours: the teams just above and below us ---------------------------------------------------------

def booked_airline(board: dict, rnd: dict, team: str) -> str | None:
    start, end = ts(rnd["sent_at"]), ts(rnd["expires_at"]) + 30
    return next((b["airline"] for b in board.get("bookings", [])
                 if b["team"] == team and start <= ts(b["booked_at"]) <= end), None)


def check_neighbors(state: dict, board: dict, now: float) -> list[tuple[bool, str]]:
    """What the teams ranked just above and below us get right and wrong, round by round (public board only)."""
    ranking = sorted(board["ranking"], key=lambda t: t["rank"])
    i = next(i for i, t in enumerate(ranking) if t["name"] == TEAM)
    us, nbs = ranking[i], [ranking[j] for j in (i - 1, i + 1) if 0 <= j < len(ranking)]
    rounds = sorted((r for r in board.get("rounds", []) if not r["voided"]), key=lambda r: r["round_no"])
    live = next((r for r in rounds if r["status"] == "open"), None)
    prev, rec, out = state.setdefault("teams", {}), state.setdefault("nb_rounds", {}), []
    for t in [us, *nbs]:
        p = prev.get(t["name"])
        pend = [x for x in rounds if x["round_no"] not in state.get("nb_done", [])]
        if p and pend:  # counters and points can land in different polls: points = jumps of up to 60
            e = rec.setdefault(str((live or pend[-1])["round_no"]), {}).setdefault(t["name"], {})
            if live and t["answered"] > p["answered"]:
                e["answered"] = True
            if live and t["accepted"] > p["accepted"]:
                e["accepted"] = True
            if 0 < (d := round(t["total"] - p["total"], 2)) <= 60.5 and d != 10:
                e["points"] = round(e.get("points", 0) + d, 2)
        if p and t["name"] != TEAM and t["human"] > p["human"]:
            out.append((True, f"{t['name']} (rank {t['rank']}) got the humanity bonus: their emails won the jury's +10"))
        prev[t["name"]] = {k: t[k] for k in ("answered", "accepted", "total", "human")}
    if (last := state.get("our_rank")) and last != us["rank"]:
        above = f", now behind {ranking[i - 1]['name']}" if i > 0 and us["rank"] > last else ""
        out.append((us["rank"] > last, f"Rank {last} -> {us['rank']}{above}"))
    state["our_rank"] = us["rank"]
    done = state.setdefault("nb_done", [r["round_no"] for r in rounds])  # first run: don't report the past
    for rnd in rounds:
        n = rnd["round_no"]
        if n in done or now < ts(rnd["expires_at"]) + 60:
            continue
        done.append(n)
        e = rec.pop(str(n), {})
        ours = e.get(TEAM, {})
        for t in nbs:
            theirs, airline = e.get(t["name"], {}), booked_airline(board, rnd, t["team"])
            via = f" with {airline}" if airline else ""
            if theirs.get("accepted") and not ours.get("accepted"):
                out.append((True, f"Round {n}: {t['name']} (rank {t['rank']}) got it accepted{via}, we didn't"))
            elif theirs.get("accepted") and ours.get("accepted") and theirs.get("points") and ours.get("points") and theirs["points"] - ours["points"] >= 1:
                out.append((True, f"Round {n}: {t['name']} scored {theirs['points']:.2f} vs our "
                                  f"{ours.get('points', 0):.2f}{via}: they priced closer to the best"))
            elif ours.get("accepted") and theirs.get("answered") and not theirs.get("accepted"):
                out.append((False, f"Round {n}: {t['name']} (rank {t['rank']}) failed where we scored"))
    return out


def gaps(board: dict) -> str:
    ranking = sorted(board["ranking"], key=lambda t: t["rank"])
    i = next(i for i, t in enumerate(ranking) if t["name"] == TEAM)
    parts = []
    if i > 0:
        parts.append(f"{ranking[i - 1]['total'] - ranking[i]['total']:.0f} behind {ranking[i - 1]['name']}")
    if i + 1 < len(ranking):
        parts.append(f"{ranking[i]['total'] - ranking[i + 1]['total']:.0f} ahead of {ranking[i + 1]['name']}")
    return "; ".join(parts)


# ---- key mode (needs FIVEU_API_KEY) ------------------------------------------------------------------------

def requests_of(me: dict) -> list[dict]:
    # Live /v1/board/me items (Sat 16:55): round_no, sent_at, answered_at, verdict, reason, booked. No points or price
    # while scores_revealed is false; those keys stay as fallbacks.
    items = me.get("requests") or next((v for k, v in me.items() if isinstance(v, list) and k != "bookings"), [])
    return [{
        "round": i.get("round_no") or i.get("round") or i.get("id"),
        "verdict": (i.get("verdict") or "").lower(),
        "reason": i.get("reason") or i.get("reason_code"),
        "points": i.get("points") or {},
        "price": i.get("price") or i.get("total_price"),
        "booked": i.get("booked"),
        "answered_at": i.get("answered_at"),
        "sent_at": i.get("sent_at"),
        "keys": sorted(i),
    } for i in items]


def baseline_me(state: dict, me: dict) -> None:
    """Mark what /v1/board/me already shows as seen, so starting in key mode doesn't replay old alerts."""
    for r in requests_of(me):
        if r["verdict"] not in ("", "open", "pending") and r["round"] not in state["seen"]:
            state["seen"].append(r["round"])
        if r["reason"] and r["reason"] not in state["reasons"]:
            state["reasons"].append(r["reason"])
        if r["verdict"] == "accepted" and r["booked"] is False:
            state.setdefault("unbooked", []).append(r["round"])
    state["me_base"] = True


def best_price(our_price: float, accuracy: float) -> float:
    """True best price from our price and accuracy points, assuming points fall linearly from 45 at best to 0 at +5%."""
    return our_price / (1 + ACCEPT_BAND * (1 - accuracy / ACCURACY_MAX))


def check(state: dict, me: dict, board: dict, now: float | None = None) -> list[str]:
    """Alerts for requests scored since the last check. `state` remembers seen rounds and reason codes."""
    alerts, now = [], now or time.time()
    # 5U's exact points per request (time, accuracy, booking, tracking), there since ~18:50
    scored = [r for r in requests_of(me) if r["verdict"] == "accepted" and "accuracy" in r["points"]]
    if "scored" not in state:  # first time: don't replay old rounds
        state["scored"] = [r["round"] for r in scored]
    for r in scored:
        if r["round"] in state["scored"]:
            continue
        state["scored"].append(r["round"])
        acc, tm = r["points"].get("accuracy", 0), r["points"].get("time", TIME_MAX)
        if acc < ACCURACY_MAX - 0.5:
            alerts.append(f"Round {r['round']} accuracy {acc:g}/45: about "
                          f"{ACCEPT_BAND * (1 - acc / ACCURACY_MAX):.1%} above the best price")
        if tm < TIME_MAX - 0.5:
            alerts.append(f"Round {r['round']} time points {tm:g}/15: our quote was too slow")
    # cost arrives hourly, after the round: watch it and the unexplained "booking" category separately
    costed = [r for r in requests_of(me) if "cost" in r["points"] or r["points"].get("booking")]
    if "costed" not in state:
        state["costed"] = [r["round"] for r in costed]
    for r in costed:
        if r["round"] in state["costed"]:
            continue
        state["costed"].append(r["round"])
        cost, booking = r["points"].get("cost"), r["points"].get("booking") or 0
        if cost is not None and cost < 39:
            alerts.append(f"Round {r['round']} cost points {cost:g}/40: extra gateway spend (bid-parser or "
                          f"re-read LLM calls, or testing on the live key)")
        if booking:
            alerts.append(f"Round {r['round']} earned {booking:g} BOOKING points (always 0 before): find out what "
                          f"this round did differently")
    # penalties (round 48/49: -22.5 for booking at a price that changed after the customer's yes, EMERGENCY_FIXES #10)
    adjusted = [r for r in requests_of(me) if r["points"].get("adjustment")]
    if "adjusted" not in state:
        state["adjusted"] = [r["round"] for r in adjusted]
    for r in adjusted:
        if r["round"] not in state["adjusted"]:
            state["adjusted"].append(r["round"])
            alerts.append(f"Round {r['round']} PENALTY {r['points']['adjustment']:g} (adjustment): likely booked at a "
                          f"changed price without asking the customer again (EMERGENCY_FIXES #10)")
    for r in requests_of(me):  # accepted but 5U doesn't count a booking: that round earns no tracking +10
        if (r["verdict"] == "accepted" and r["booked"] is False and r["answered_at"]
                and now - ts(r["answered_at"]) > 660 and r["round"] not in state.setdefault("unbooked", [])):
            state["unbooked"].append(r["round"])
            alerts.append(f"Round {r['round']} accepted but NOT booked 11 min later (5U checks at 10 min): no tracking +10 "
                          f"(check its booking events on the Mac)")
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

URGENT = ("no answer from us", "NOT accepted", "not accepted:", "closed with NO answer", "PENALTY")


def priority_of(text: str) -> tuple[str, str]:
    """ntfy (priority, tag): 5 breaks through do-not-disturb, 1 is a silent heartbeat."""
    if text.startswith("Watcher alive"):
        return "1", "heartbeat"
    if any(s in text for s in URGENT):
        return "5", "rotating_light"
    if "after all" in text or "back online" in text:
        return "3", "white_check_mark"
    return "4", "warning"


# ntfy.sh allows an anonymous sender only a limited number of messages a day (HTTP 429 after that). Routine lines
# (accepted rounds, tracking bonus, cost points, RFQ briefs, "they priced closer") stay in watch.log only; the phone
# gets what needs a person: penalties, 0-point or rejected rounds, missed answers, humanity bonuses, new reason codes,
# outages and the 30-min heartbeat. On a 429 we wait BACKOFF_S and then send everything held back as ONE message.
ROUTINE = ("accepted: +", "Tracking bonus", "Cost points posted", " RFQ: ", "priced closer to the best",
           "failed where we scored", "heads-up:", "accuracy ")
IMPORTANT = ("PENALTY", "accepted: +0.00", "NOT accepted", "not accepted", "no answer", "humanity bonus", "reason",
             "can't reach", "back online", "rejected", "voided", "Watcher alive")
BACKOFF_S = float(os.environ.get("NTFY_BACKOFF_SECONDS", "600"))
_held: list[str] = []
_backoff_until = 0.0


def _worth_a_push(text: str) -> bool:
    return any(k in text for k in IMPORTANT) or not any(k in text for k in ROUTINE)


def _send(topic: str, text: str) -> bool:
    global _backoff_until
    priority, tag = priority_of(text)
    headers = {"Title": "Leylu board watcher", "Priority": priority, "Tags": tag}
    try:  # offline laptop: the push fails too, and that must never stop the watcher
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=text.encode(), headers=headers)
        urllib.request.urlopen(req, timeout=8)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 429:  # ntfy says how long: "Retry-After: 7414" when the daily quota (250/day per IP) is used up
            try:
                wait = max(BACKOFF_S, float(e.headers.get("Retry-After") or 0))
            except ValueError:
                wait = BACKOFF_S
            _backoff_until = time.time() + wait
            print(time.strftime("%H:%M:%S"), f"push held: ntfy quota used up, {len(_held)} alert(s) go out together at "
                  f"{time.strftime('%H:%M', time.localtime(_backoff_until))}", flush=True)
            return False
        print(time.strftime("%H:%M:%S"), f"push failed: {e}", flush=True)
    except Exception as e:
        print(time.strftime("%H:%M:%S"), f"push failed: {e}", flush=True)
    return False


def notify(text: str, push: bool = True) -> None:
    print(time.strftime("%H:%M:%S"), text, flush=True)
    topic = os.environ.get("NTFY_TOPIC")
    if not (push and topic and _worth_a_push(text)):  # phone push via ntfy.sh, only when a topic is set
        return
    _held.append(text)
    del _held[:-15]  # never more than the last 15 alerts in one bundle
    if time.time() < _backoff_until:
        return  # ntfy said 429: wait, the held alerts go out together after the backoff
    bundle = _held[0] if len(_held) == 1 else f"{len(_held)} alerts:\n" + "\n".join(f"- {t}" for t in _held)
    if _send(topic, bundle):
        _held.clear()


def flush_held() -> None:
    """Called every poll: sends the held alerts once the backoff is over, even when no new alert comes."""
    if _held and time.time() >= _backoff_until and (topic := os.environ.get("NTFY_TOPIC")):
        bundle = _held[0] if len(_held) == 1 else f"{len(_held)} alerts:\n" + "\n".join(f"- {t}" for t in _held)
        if _send(topic, bundle):
            _held.clear()


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
    # start reading the mailbox near its end, never from the first mail (MAIL_SINCE seeds it once)
    MAILBOX["since"] = state.get("mail_since") or int(os.environ.get("MAIL_SINCE", "0"))
    while True:
        started = time.time()
        flush_held()
        try:
            board = read(args.board) if args.board else get("/v1/board")
            if failures:  # each poll reads the full board, so nothing that happened meanwhile is lost
                notify(f"Board watcher back online (offline since {offline_since}, {failures} failed polls)")
            failures = 0
            if started - last_beat > HEARTBEAT_S:  # so a reader can tell "all quiet" from "watcher dead"
                last_beat, us = started, next(t for t in board["ranking"] if t["name"] == TEAM)
                notify(f"Watcher alive: rank {us['rank']}, {us['total']:.2f} pts, "
                       f"{us['accepted']}/{us['answered']} accepted; {gaps(board)}")
            for push, text in check_public(state, board, time.time()) + check_neighbors(state, board, time.time()):
                notify(text, push)
            if args.me or key:
                me = read(args.me) if args.me else get("/v1/board/me", key)
                if key and not args.me and "me_base" not in state:
                    baseline_me(state, me)
                for text in check(state, me, board, time.time()):
                    notify(text)
                if key and not args.me:  # heads-up on a new round's RFQ before we quote (docs/POSSIBLE_TRAPS.md)
                    for rnd in board.get("rounds", []):
                        if (rnd["status"] == "open" and rnd["round_no"] not in state.setdefault("prechecked", [])
                                and time.time() - ts(rnd["sent_at"]) >= 20):  # after the agent has fetched the RFQ
                            state["prechecked"].append(rnd["round_no"])
                            try:
                                if (m := find_rfq(key, rnd["sent_at"])) and (hits := trap_signals(key, m)):
                                    notify(f"Round {rnd['round_no']} heads-up: {'; '.join(hits)} "
                                           f"('{m.get('subject')}'): check the quote before it goes out")
                            except Exception as e:
                                print(time.strftime("%H:%M:%S"), f"precheck failed: {e}", flush=True)
                if key and not args.me:  # who sent what: the RFQ and what its attachments declare
                    for r in requests_of(me):
                        if (r["verdict"] in BAD and r["sent_at"] and time.time() - ts(r["sent_at"]) < 900
                                and r["round"] not in state.setdefault("briefed", [])):
                            state["briefed"].append(r["round"])
                            brief = rfq_brief(key, r["sent_at"])
                            notify(f"Round {r['round']} RFQ: {brief}")
                            log_incident(r, brief, board)
            state["mail_since"] = MAILBOX["since"]
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

