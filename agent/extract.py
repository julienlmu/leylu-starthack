"""RFQ extraction: the one gateway call per RFQ.

The model only copies what the mail says (numbers as written, plus their units). All unit
conversion happens in to_rfq(), because numbers come from code, never from the LLM.
"""

import csv
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
    "covers all pieces of that line. pickup_address only if the customer wants pickup at their address. "
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
                "required": ["count", "length", "width", "height", "weight", "weight_is_total"],
                "properties": {"count": {"type": "integer"}, "length": _NUM, "width": _NUM, "height": _NUM,
                               "weight": _NUM, "weight_is_total": {"type": "boolean"}},
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


def extract(mail: dict) -> tuple[dict, float]:
    """Returns (raw extraction, cost in USD)."""
    sent = f"Date: {mail['received_at'][:10]}\n" if mail.get("received_at") else ""  # lets "ab 23.11." get the right year
    return llm.chat_json("rfq", SYSTEM, f"{sent}Subject: {mail['subject']}\n\n{mail['body']}", SCHEMA)


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
        "volume_m3": raw["volume_m3"],
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
