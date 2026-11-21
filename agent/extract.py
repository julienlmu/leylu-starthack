"""RFQ extraction: the one gateway call per RFQ.

The model only copies what the mail says (numbers as written, plus their units). All unit
conversion happens in to_rfq(), because numbers come from code, never from the LLM.
"""

import csv
import os
import re
from pathlib import Path

import llm
from carriers import pickup_zone

# Pickup zone (first two postcode digits) → origin airport, the same file the backend prices with.
ZONES = Path(__file__).resolve().parent.parent / "backend" / "data" / "pickup_zones.csv"


def zone_airport(pickup: dict | None) -> str | None:
    zone = pickup_zone(pickup)
    if not zone or not ZONES.exists():
        return None
    with ZONES.open(newline="") as f:
        return next((row["airport"] for row in csv.DictReader(f) if row["zone"] == zone), None)

SYSTEM = (
    "Extract the air freight request from the email. Airports as IATA codes. "
    "ask: did the customer ask for the cheapest or the fastest option. "
    "Copy numbers exactly as written and give their units. weight_is_total is true when the weight "
    "covers all pieces of that line. A volume given per line or lot goes into that piece line's volume_m3 "
    "(cubic metres for the whole line); a single volume for the whole shipment goes into the top-level volume_m3. "
    "pickup_address only if the customer wants pickup at their address. "
    "Unknown values are null."
)

_NUM = {"type": ["number", "null"]}
_STR = {"type": ["string", "null"]}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["origin", "destination", "ask", "pickup_address", "ready_date", "pieces", "dim_unit",
                 "weight_unit", "volume_m3", "commodity", "dangerous_goods", "customer_reference", "language"],
    "properties": {
        "origin": _STR,
        "destination": _STR,
        "ask": {"type": ["string", "null"], "enum": ["cheapest", "fastest", None]},
        "pickup_address": _STR,
        "ready_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "pieces": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["count", "length", "width", "height", "weight", "weight_is_total", "volume_m3"],
                "properties": {"count": {"type": "integer"}, "length": _NUM, "width": _NUM, "height": _NUM,
                               "weight": _NUM, "weight_is_total": {"type": "boolean"}, "volume_m3": _NUM},
            },
        },
        "dim_unit": {"type": "string", "enum": ["cm", "mm", "m", "in"]},
        "weight_unit": {"type": "string", "enum": ["kg", "lb"]},
        "volume_m3": _NUM,
        "commodity": _STR,
        "dangerous_goods": {"type": "boolean"},
        "customer_reference": _STR,
        "language": {"type": "string", "description": "ISO 639-1 code of the email's language"},
    },
}

TO_CM = {"cm": 1.0, "mm": 0.1, "m": 100.0, "in": 2.54}
TO_KG = {"kg": 1.0, "lb": 0.45359237}


# Orchestrator and actors: the cheap model reads every mail; plain code (free) checks the result, and only a result that
# fails the checks is read again by the stronger model. Easy mails cost ~$0.0001, a hard one ~$0.001 more.
ESCALATION_MODEL = os.environ.get("LLM_ESCALATION_MODEL") or "gpt-6.1-terra"
IATA = re.compile(r"^[A-Z]{3}$")


def extract(mail: dict, model: str = llm.MODEL) -> tuple[dict, float]:
    """Returns (raw extraction, cost in USD)."""
    sent = f"Date: {mail['received_at'][:10]}\n" if mail.get("received_at") else ""  # lets "ab 23.11." get the right year
    return llm.chat_json("rfq", SYSTEM, f"{sent}Subject: {mail['subject']}\n\n{mail['body']}", SCHEMA, model=model)


def doubts(rfq: dict) -> list[str]:
    """Free plausibility checks on an extraction: what a careful forwarder would question before pricing."""
    found = [f"{f} is not an airport code" for f in ("origin", "destination") if rfq[f] and not IATA.match(rfq[f])]
    for p in rfq["pieces"]:
        if p["weight_kg"] is not None and not 0 < p["weight_kg"] <= 30000:
            found.append(f"implausible weight {p['weight_kg']} kg per piece")
        if any(d is not None and not 0 < d <= 2000 for d in (p["length_cm"], p["width_cm"], p["height_cm"])):
            found.append("implausible dimensions")
    dims = rfq["pieces"] and all(p["length_cm"] and p["width_cm"] and p["height_cm"] for p in rfq["pieces"])
    if dims and rfq["volume_m3"]:
        computed = sum(p["count"] * p["length_cm"] * p["width_cm"] * p["height_cm"] for p in rfq["pieces"]) / 1e6
        if not 0.75 <= computed / rfq["volume_m3"] <= 1.33:
            found.append(f"dimensions give {computed:.2f} m3 but the mail says {rfq['volume_m3']} m3")
    return found


def read_request(mail: dict) -> dict:
    """Orchestrator: cheap actor first; escalate to the stronger actor only if the result is incomplete or implausible.

    Returns {rfq, missing, cost, model, escalated: reasons or None}.
    """
    raw, cost = extract(mail)
    rfq, missing = to_rfq(raw)
    reasons = [f"missing {m}" for m in missing] + doubts(rfq)
    if not reasons:
        return {"rfq": rfq, "missing": missing, "cost": cost, "model": llm.MODEL, "escalated": None}
    try:
        raw2, cost2 = extract(mail, ESCALATION_MODEL)
    except Exception as error:  # the stronger actor failing must never cost us the cheap result
        return {"rfq": rfq, "missing": missing, "cost": cost, "model": llm.MODEL,
                "escalated": reasons + [f"escalation failed: {type(error).__name__}"]}
    rfq2, missing2 = to_rfq(raw2)
    if len(missing2) + len(doubts(rfq2)) <= len(reasons):  # not worse: trust the stronger reader
        return {"rfq": rfq2, "missing": missing2, "cost": cost + cost2, "model": ESCALATION_MODEL, "escalated": reasons}
    return {"rfq": rfq, "missing": missing, "cost": cost + cost2, "model": llm.MODEL, "escalated": reasons}


def _line_volumes(pieces: list[dict]) -> float | None:
    """The shipment's volume from per-line volumes ("Lot 1 … 0.74 cbm, Lot 2 … 1.65 cbm" → 2.39), if every line has one."""
    volumes = [p.get("volume_m3") for p in pieces]
    if not volumes or any(v is None for v in volumes):
        return None
    return round(sum(volumes), 6)


def to_rfq(raw: dict) -> tuple[dict, list[str]]:
    """Raw extraction → contract Rfq (cm, kg per piece) and the list of fields we can't price without."""
    cm, kg = TO_CM[raw["dim_unit"]], TO_KG[raw["weight_unit"]]
    pieces = []
    for p in raw["pieces"]:
        count = p["count"] or 1
        weight = p["weight"] / count if p["weight"] is not None and p["weight_is_total"] else p["weight"]
        pieces.append({
            "count": count,
            "length_cm": round(p["length"] * cm, 1) if p["length"] is not None else None,
            "width_cm": round(p["width"] * cm, 1) if p["width"] is not None else None,
            "height_cm": round(p["height"] * cm, 1) if p["height"] is not None else None,
            "weight_kg": round(weight * kg, 2) if weight is not None else None,
        })
    rfq = {
        "origin": raw["origin"],
        "destination": raw["destination"],
        "ask": raw["ask"] or "cheapest",
        "pickup": {"address": raw["pickup_address"], "zone": None} if raw["pickup_address"] else None,
        "ready_date": raw["ready_date"],
        "pieces": pieces,
        "volume_m3": raw["volume_m3"] if raw["volume_m3"] is not None else _line_volumes(raw["pieces"]),
        "commodity": raw["commodity"],
        "dangerous_goods": raw["dangerous_goods"],
        "customer_reference": raw["customer_reference"],
        "language": raw["language"],
    }
    if rfq["pickup"] and (airport := zone_airport(rfq["pickup"])):
        rfq["origin"] = airport  # door-to-port flies from the pickup zone's airport (Bergisch Gladbach 51 → CGN)
    missing = [f for f in ("origin", "destination") if not rfq[f]]
    if not pieces or any(p["weight_kg"] is None for p in pieces):
        missing.append("weight")
    has_dims = pieces and all(p["length_cm"] and p["width_cm"] and p["height_cm"] for p in pieces)
    if not has_dims and rfq["volume_m3"] is None:
        missing.append("dimensions or volume")
    return rfq, missing
