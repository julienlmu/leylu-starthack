"""PORTAL_MEMORY (default on; off = no remembered rates): the portal's past answers, reused while its API fails.

R93/R94: the rate portal API answered 503 for a whole round. Every team quoted the sheet and was rejected too_low,
because 5U's reference was the portal price. The portal prices "in the bracket of the weight you enter", so a portal
answer we already got for the same lane and airline gives the per-kg all-in rate (freight + fuel + security) of
its bracket. Every /api/price result the agent logged ("priced" events) holds those portal options.

options(origin, destination, airlines, chargeable): one option per lane airline ({code, name}) the live portal didn't
price (pricing.Pricer._remembered: its rate call just failed), from the newest remembered answer (at most MAX_AGE_S old)
in the same weight bracket (the airline's breaks), scaled per kg: freight + fuel + security are all per billed kg there.
Never another bracket's rate (another per-kg price, >5 % off = rejected). The lowest bracket (its minimum charge may
bind) and an airline whose breaks are unknown: only the exact same billed weight.
Source "portal" with `remembered` = "bracket" | "weight", no rate ID (the booking books a fresh rate and asks the
customer again if it differs, or books by email while the portal is down).

PORTAL_SURGE (default on; R122 too_low): the portal raises every airline's rate at once for a while, by fixed steps
(night of 21/22 Nov: x1.15 from 20:05 to 20:29, x1.30 from 20:35 to 20:41, the same factor for every airline of the
round). A remembered answer from such a window was the surged price, and an unsurged one is too low while a surge
runs. So every remembered answer is brought back to its base (its lowest same-airline, same-lane answer that is one
surge step below it), and the remembered option is the base times the factor in force now: read from a live portal
answer of this same pricing (the web form, a rate a person pasted) against its remembered base, else from the newest
live answer of the last SURGE_WINDOW_S, else 1 (no surge known).
"""

import json
import os
import time
from datetime import datetime, timezone

ON = os.environ.get("PORTAL_MEMORY", "on").lower() != "off"
# Portal rates come from a dataset that can change (tariffs by validity period): older answers are not reused
MAX_AGE_S = float(os.environ.get("PORTAL_MEMORY_MAX_AGE_H", "24")) * 3600
SCAN_EVENTS = 5000  # newest "priced" events looked at
TTL_S = 30  # the index is rebuilt at most this often
SURGE = os.environ.get("PORTAL_SURGE", "on").lower() != "off"
LEVELS = tuple(float(x) for x in os.environ.get("PORTAL_SURGE_LEVELS", "1.15,1.30").split(",") if x.strip())
SURGE_WINDOW_S = float(os.environ.get("PORTAL_SURGE_WINDOW_MIN", "30")) * 60
CONFIRM_S = 30 * 60
MATCH = 0.01  # a ratio within 1 % of a surge step is that step (the portal's steps are exact: 1.149-1.151, 1.299-1.304)


def _step(ratio: float) -> float | None:
    """The surge step a ratio of two same-airline per-kg rates is (1.0 = the same rate), or None."""
    for level in (1.0, *LEVELS):
        if abs(ratio / level - 1) <= MATCH:
            return level
    return None


class PortalMemory:
    def __init__(self, crm, lane):
        """crm: crm.Crm (its SQLite connection); lane(rfq) → (origin, destination) the way the pricer prices it."""
        self.crm, self.lane, self._index, self._built = crm, lane, {}, 0.0
        self._timeline: list[tuple[float, float]] = []  # (event time, surge factor that pricing ran at), newest first

    def _rebuild(self) -> None:
        index: dict[tuple[str, str], list[dict]] = {}
        rows = self.crm.db.execute(
            "SELECT e.id, e.at, e.text, e.data, s.id AS sid, s.rfq FROM events e JOIN sessions s ON s.id = e.session_id "
            "WHERE e.kind = 'priced' AND e.at >= ? ORDER BY e.id DESC LIMIT ?",
            (datetime.fromtimestamp(time.time() - MAX_AGE_S, timezone.utc).isoformat(timespec="seconds"),
             SCAN_EVENTS)).fetchall()
        for row in rows:
            text = row["text"] or ""
            if text.startswith(("Shipment to", "No price at")):  # another lot's lane, or an alias airport's lane
                continue
            try:
                data, rfq = json.loads(row["data"] or "{}"), json.loads(row["rfq"] or "null")
            except ValueError:
                continue
            if not isinstance(data, dict) or not isinstance(rfq, dict):
                continue
            try:
                origin, destination = self.lane(rfq)
            except Exception:
                continue
            for option in data.get("options") or []:
                if not isinstance(option, dict) or option.get("source") != "portal" or option.get("remembered"):
                    continue
                try:
                    billed = float(option.get("billed_weight_kg") or option.get("chargeable_weight_kg") or 0)
                    air = float(option.get("total_eur") or option["total"]) \
                        - float((option.get("pickup") or {}).get("total") or 0) \
                        - float((option.get("insurance") or {}).get("total") or 0) - float(option.get("insurance_eur") or 0)
                except (KeyError, TypeError, ValueError):
                    continue
                if billed <= 0 or air <= 0:
                    continue
                index.setdefault((origin, destination), []).append({
                    "code": option.get("airline_code") or option.get("carrier"), "carrier": option.get("carrier"),
                    "per_kg": air / billed, "billed": billed, "transit_days": option.get("transit_days"),
                    "session": row["sid"], "event": row["id"], "at": _epoch(row["at"])})
        self._index, self._built = index, time.time()
        self._timeline = _surges(index) if SURGE else []

    def rates(self, origin: str, destination: str) -> list[dict]:
        if time.time() - self._built > TTL_S:
            self._rebuild()
        return self._index.get((origin.upper(), destination.upper()), [])

    def factor(self, origin: str, destination: str, live: list[dict] = (), now: float | None = None) -> tuple[float, str]:
        """The surge factor in force now and where it was read: a live answer of this pricing (web form, a pasted portal
        rate: {code, carrier, per_kg, billed}) against its remembered base, else the newest live answer of the last
        SURGE_WINDOW_S, else 1.0."""
        if not SURGE:
            return 1.0, ""
        seen = self.rates(origin, destination)
        for rate in live:
            same = sorted((r for r in seen if r["code"] == rate.get("code") or r["carrier"] == rate.get("carrier")),
                          key=lambda r: abs(r["billed"] - rate["billed"]))  # the nearest weight: most likely its bracket
            for r in same[:1]:
                if step := _step(rate["per_kg"] / r["base"]):
                    return step, f"live {rate.get('carrier') or rate.get('code')} rate now vs its base"
        now = time.time() if now is None else now
        for at, step in self._timeline:
            if now - at <= SURGE_WINDOW_S:
                return step, f"newest live portal answer {int((now - at) // 60)} min ago"
            break
        return 1.0, ""

    def options(self, origin: str, destination: str, airlines: list[dict], chargeable: float,
                live: list[dict] = ()) -> list[dict]:
        """airlines: [{code, name, breaks?}]; breaks (the airline's weight breaks, if known) keep it to the same bracket.
        live: this pricing's live answers for other airlines of the lane (PORTAL_SURGE reads the factor from them)."""
        if not ON or chargeable <= 0:
            return []
        factor, source = self.factor(origin, destination, live)
        out = []
        for airline in airlines:
            code, name, breaks = airline.get("code"), airline.get("name"), sorted(airline.get("breaks") or [])
            seen = [r for r in self.rates(origin, destination) if r["code"] == code or (name and r["carrier"] == name)]
            exact = [r for r in seen if abs(r["billed"] - chargeable) < 0.01]
            # the lowest bracket may be billed at its minimum charge: not per kg
            per_kg = len(breaks) > 1 and chargeable >= breaks[1]
            same = [r for r in seen if per_kg and r["billed"] >= breaks[1]
                    and _bracket(r["billed"], breaks) == _bracket(chargeable, breaks)]
            if not (exact or same):
                continue
            best = (exact or same)[0] if exact else min(same, key=lambda r: abs(r["billed"] - chargeable))  # newest first
            per_kg = best["per_kg"]
            surge = ""
            if SURGE and best.get("base") and abs(best["base"] * factor - per_kg) > 1e-9:
                per_kg = best["base"] * factor
                surge = (f", surge x{best['per_kg'] / best['base']:.2f} then, x{factor:.2f} now"
                         + (f" ({source})" if source else ""))
            total = round(per_kg * chargeable, 2)
            kind = "weight" if exact else "bracket"
            label = (f"Air freight {best['carrier']} (portal rate remembered from session #{best['session']}, same {kind}: "
                     f"EUR {best['per_kg']:.4f}/kg at {best['billed']:g} kg{surge}, EUR {per_kg:.4f}/kg × {chargeable:g} kg)")
            out.append({"source": "portal", "remembered": kind, "leg": "air",
                        "carrier": best["carrier"], "airline_code": code, "rate_id": None, "currency": "EUR",
                        "total": total, "total_eur": total, "transit_days": best["transit_days"], "valid_until": None,
                        "chargeable_weight_kg": chargeable, "billed_weight_kg": chargeable,
                        "breakdown": [{"label": label, "amount": total}]})
        return out


def _epoch(at) -> float:
    try:
        return datetime.fromisoformat(str(at)).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _surges(index: dict) -> list[tuple[float, float]]:
    """Sets each remembered answer's `base` (its per-kg rate without a surge) and returns (time, factor) per priced
    event whose factor is known, newest first.

    Per lane and airline, an answer's step is its ratio to the lowest answer it is one surge step (or 0) above. A priced
    event's factor counts only when its answers agree, and a surge (not 1.0) only when two or more airlines of the
    event show the same step, and another lane within CONFIRM_S shows it too: a bracket may happen to differ by 15 %.
    An answer of an event without a known factor is taken as unsurged (surges are short)."""
    steps: dict[int, list[float]] = {}
    when: dict[int, float] = {}
    for rates in index.values():
        by_code: dict = {}
        for r in rates:
            by_code.setdefault(r["code"], []).append(r)
        for group in by_code.values():
            for r in group:
                below = [o["per_kg"] for o in group if o is not r and _step(r["per_kg"] / o["per_kg"])]
                above = [o for o in group if o is not r and _step(o["per_kg"] / r["per_kg"])]
                when[r["event"]] = r["at"]
                if below or above:
                    steps.setdefault(r["event"], []).append(_step(r["per_kg"] / min(below + [r["per_kg"]])))
    lane_of = {r["event"]: lane for lane, rates in index.items() for r in rates}
    agreed = {e: found[0] for e, found in steps.items()
              if len(set(found)) == 1 and (found[0] == 1.0 or len(found) >= 2)}
    # a surge is the whole portal's: another lane must show the same step within CONFIRM_S (two brackets of one lane
    # can differ by ~15 % too: STR-MEL 1,615 vs 2,000 kg)
    factor = {e: f for e, f in agreed.items() if f == 1.0 or any(
        o != e and g == f and lane_of.get(o) != lane_of.get(e) and abs(when[o] - when[e]) <= CONFIRM_S
        for o, g in agreed.items())}
    for rates in index.values():
        for r in rates:
            r["base"] = r["per_kg"] / factor.get(r["event"], 1.0)
    return sorted(((when[e], f) for e, f in factor.items() if when.get(e)), reverse=True)


def _bracket(weight: float, breaks: list[float]) -> float:
    """The break whose bracket holds this weight (a bracket runs from its break to the next)."""
    return max([b for b in breaks if b <= weight], default=breaks[0])
