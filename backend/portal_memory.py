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


class PortalMemory:
    def __init__(self, crm, lane):
        """crm: crm.Crm (its SQLite connection); lane(rfq) → (origin, destination) the way the pricer prices it."""
        self.crm, self.lane, self._index, self._built = crm, lane, {}, 0.0

    def _rebuild(self) -> None:
        index: dict[tuple[str, str], list[dict]] = {}
        rows = self.crm.db.execute(
            "SELECT e.id, e.text, e.data, s.id AS sid, s.rfq FROM events e JOIN sessions s ON s.id = e.session_id "
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
                    "session": row["sid"]})
        self._index, self._built = index, time.time()

    def rates(self, origin: str, destination: str) -> list[dict]:
        if time.time() - self._built > TTL_S:
            self._rebuild()
        return self._index.get((origin.upper(), destination.upper()), [])

    def options(self, origin: str, destination: str, airlines: list[dict], chargeable: float) -> list[dict]:
        """airlines: [{code, name, breaks?}]; breaks (the airline's weight breaks, if known) keep it to the same bracket."""
        if not ON or chargeable <= 0:
            return []
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
            total = round(best["per_kg"] * chargeable, 2)
            kind = "weight" if exact else "bracket"
            label = (f"Air freight {best['carrier']} (portal rate remembered from session #{best['session']}, same {kind}: "
                     f"EUR {best['per_kg']:.4f}/kg at {best['billed']:g} kg, × {chargeable:g} kg)")
            out.append({"source": "portal", "remembered": kind, "leg": "air",
                        "carrier": best["carrier"], "airline_code": code, "rate_id": None, "currency": "EUR",
                        "total": total, "total_eur": total, "transit_days": best["transit_days"], "valid_until": None,
                        "chargeable_weight_kg": chargeable, "billed_weight_kg": chargeable,
                        "breakdown": [{"label": label, "amount": total}]})
        return out


def _bracket(weight: float, breaks: list[float]) -> float:
    """The break whose bracket holds this weight (a bracket runs from its break to the next)."""
    return max([b for b in breaks if b <= weight], default=breaks[0])
