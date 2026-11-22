"""SHARED_PICKUP (default off; on = one truck for all lots): several shipments in one RFQ (MULTI_QUOTE) that are picked
up at the same site on the same day travel on ONE truck to the airport.

R113 (MUC → RUH 749 kg / 4.8 cbm and DXB 1,239 kg / 5.27 cbm, one site in Munich, accuracy 41.08 = ~0.9 % off): the
truckers were asked for lot 1's weight only and lot 2 was quoted with that same truck price (EUR 131.11 for 801.6
chargeable kg), although a trucker prices base + EUR/kg × chargeable kg (backend/pickup_reuse.py). On: the truckers
are asked once for all lots together (one truck), and each lot carries its share of that truck price by chargeable
weight (the shares add up to the truck price). Off, or lots from different sites / days: as before.
"""

import os

ON = os.environ.get("SHARED_PICKUP", "off").lower() == "on"
CBM_KG = 167.0


def _lots(rfq: dict) -> list[dict]:
    return [{k: v for k, v in rfq.items() if k != "other_lots"}, *(rfq.get("other_lots") or [])]


def _chargeable(lot: dict) -> float:
    kg = sum(int(p.get("count") or 1) * float(p.get("weight_kg") or 0) for p in lot.get("pieces") or [])
    return max(kg, float(lot.get("volume_m3") or 0) * CBM_KG)


def combined(rfq: dict) -> dict | None:
    """The request the truckers get (all lots on one truck), or None when there is nothing to share."""
    if not ON or not rfq.get("other_lots") or not rfq.get("pickup"):
        return None
    lots = _lots(rfq)
    address = {((l.get("pickup") or {}).get("address") or "").strip().lower() for l in lots}
    if len(address) != 1 or len({l.get("ready_date") for l in lots}) != 1 or len({l.get("origin") for l in lots}) != 1:
        return None  # two sites, two days or two airports: two trucks
    if any(_chargeable(l) <= 0 for l in lots):
        return None
    volumes = [l.get("volume_m3") for l in lots]
    return {**lots[0], "pieces": [{"length_cm": None, "width_cm": None, "height_cm": None, **p} for l in lots
                                  for p in l.get("pieces") or []],
            "volume_m3": round(sum(float(v) for v in volumes), 3) if all(v is not None for v in volumes) else None}


def shares(rfq: dict) -> list[float]:
    """Each lot's share of the truck by chargeable weight (lot 1 first), summing to 1."""
    weights = [_chargeable(l) for l in _lots(rfq)]
    return [w / sum(weights) for w in weights] if sum(weights) > 0 else [1.0 / len(weights)] * len(weights)


def lot_bid(bid: dict, share: float) -> dict:
    """A trucker bid for the whole truck → this lot's part of it (other bids unchanged)."""
    if bid.get("leg") != "pickup" or bid.get("truck_total") is None:
        return bid
    return {**bid, "total": round(float(bid["truck_total"]) * share, 2), "truck_share": round(share, 4)}
