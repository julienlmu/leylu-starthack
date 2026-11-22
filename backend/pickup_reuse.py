"""PICKUP_LINE (default on; off = the newest bid within the weight tolerance only): earlier trucker bids priced for this
weight, for the fallback quote when no trucker answered in time.

Fitted on 232 live trucker bids (/mnt/project-files/pickup_bids.json, 22 Nov 2026): a trucker prices a pickup as
base + EUR/kg × chargeable kg (max(kg, cbm × 167)). Within one pickup zone the line is exact for most truckers (17 of 28
trucker/zone pairs with 3+ bids: residual 0.00 EUR); in a few zones the base depends on the exact address.
Leave-one-out over the bids, the error of the reused pickup as a share of the quoted all-in:
- newest bid within ±100 % weight (the live PICKUP_REUSE_TOLERANCE=1.0): 78 covered, 6 off by more than 5 %
- newest bid within ±50 %: 47 covered, none off by more than 5 %
- the trucker's line from 2+ earlier bids in the zone when they lie on one line (max residual < 1 EUR), else the
  newest bid within ±50 %: 57 covered, none off by more than 5 % (the line hits the exact price 19 of 31 times)
"""

import os

ON = os.environ.get("PICKUP_LINE", "on").lower() != "off"
COLLINEAR_EUR = 1.0  # earlier bids further off one line than this: the base depends on the address, no line


def line(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """(base, EUR/kg) when the points (kg, total) lie on one rising line with two different weights, else None."""
    if len(points) < 2 or max(kg for kg, _ in points) - min(kg for kg, _ in points) < 1:
        return None
    n = len(points)
    mx, my = sum(kg for kg, _ in points) / n, sum(t for _, t in points) / n
    slope = sum((kg - mx) * (t - my) for kg, t in points) / sum((kg - mx) ** 2 for kg, _ in points)
    base = my - slope * mx
    if slope < 0 or max(abs(base + slope * kg - t) for kg, t in points) >= COLLINEAR_EUR:
        return None
    return base, slope


def estimate(seen: dict[str, list[tuple[float, dict]]], kg: float, tolerance: float) -> list[dict]:
    """seen: trucker → [(chargeable kg of that session, its bid)], newest first. One bid per trucker for `kg`."""
    out = []
    for carrier, bids in seen.items():
        points = [(w, float(b["total"])) for w, b in bids if b.get("total") is not None
                  and (b.get("currency") or "EUR").upper() == "EUR"]
        fit = line(points) if ON else None
        if fit:
            base, slope = fit
            newest = bids[0][1]
            out.append({**newest, "rate_id": None, "carrier": carrier, "currency": "EUR",
                        "total": round(base + slope * kg, 2), "estimated_from": f"{len(points)} earlier bids, EUR "
                                                                               f"{base:.2f} + {slope:.4f}/kg"})
            continue
        near = [b for w, b in bids if abs(w - kg) <= tolerance * kg]  # trap 7: another weight is another price
        if near:
            out.append({**near[0], "rate_id": None, "carrier": carrier})
    return out
