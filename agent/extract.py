"""RFQ extraction: the one gateway call per RFQ.

The model only copies what the mail says (numbers as written, plus their units). All unit
conversion happens in to_rfq(), because numbers come from code, never from the LLM.
"""

import csv
import os
import re
from pathlib import Path

import llm
from airports import priceable
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
    "Copy numbers as written, never convert them: give their units instead (German style 1.233 kg is 1233, "
    "1.250,5 is 1250.5). weight_is_total / volume_is_total: true when the number covers all pieces of that line, "
    "false when it is per piece (each, je, cada uno, /pc). A volume given per line or lot goes into that line's "
    "volume; one volume for the whole shipment goes into the top-level volume. A line that only sums up the lots "
    "above it (Total: ...) is not a piece line. If the mail corrects earlier figures, use the corrected ones. "
    "pickup_address only if the customer wants pickup at their address. "
    "Unknown values are null."
)

_NUM = {"type": ["number", "null"]}
_STR = {"type": ["string", "null"]}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["origin", "destination", "ask", "pickup_address", "ready_date", "pieces", "dim_unit",
                 "weight_unit", "volume_unit", "volume", "commodity", "dangerous_goods", "customer_reference",
                 "language"],
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
                "required": ["count", "length", "width", "height", "weight", "weight_is_total", "volume",
                             "volume_is_total"],
                "properties": {"count": {"type": "integer"}, "length": _NUM, "width": _NUM, "height": _NUM,
                               "weight": _NUM, "weight_is_total": {"type": "boolean"}, "volume": _NUM,
                               "volume_is_total": {"type": "boolean"}},
            },
        },
        "dim_unit": {"type": "string", "enum": ["cm", "mm", "m", "in"]},
        "weight_unit": {"type": "string", "enum": ["kg", "lb", "t"]},
        "volume_unit": {"type": "string", "enum": ["m3", "ft3", "l"]},
        "volume": _NUM,
        "commodity": _STR,
        "dangerous_goods": {"type": "boolean"},
        "customer_reference": _STR,
        "language": {"type": "string", "description": "ISO 639-1 code of the email's language"},
    },
}

TO_CM = {"cm": 1.0, "mm": 0.1, "m": 100.0, "in": 2.54}
TO_KG = {"kg": 1.0, "lb": 0.45359237, "t": 1000.0}
TO_M3 = {"m3": 1.0, "ft3": 0.0283168466, "l": 0.001}


# Orchestrator and actors: the cheap model reads every mail; plain code (free) checks the result, and only a result that
# fails the checks is read again by the stronger model. Easy mails cost ~$0.0001, a hard one ~$0.001 more.
ESCALATION_MODEL = os.environ.get("LLM_ESCALATION_MODEL") or "gpt-6.1-terra"
IATA = re.compile(r"^[A-Z]{3}$")


def extract(mail: dict, model: str = llm.MODEL) -> tuple[dict, float]:
    """Returns (raw extraction, cost in USD)."""
    sent = f"Date: {mail['received_at'][:10]}\n" if mail.get("received_at") else ""  # lets "ab 23.11." get the right year
    return llm.chat_json("rfq", SYSTEM, f"{sent}Subject: {mail['subject']}\n\n{mail['body']}", SCHEMA, model=model)


# Air cargo between foam (~10 kg per m3) and solid steel parts in a crate. Outside it, a unit or a decimal was misread
# ("2.4 t" read as 2.4 kg, German "1.233 kg" as 1.233 kg): the price would be wrong, so never quote it unchecked.
DENSITY_KG_M3 = (5, 2500)
_MAIL_NUMBER = re.compile(r"\d+(?:[.,  ]\d+)*")
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "twelve": 12, "ein": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
          "un": 1, "une": 1, "deux": 2, "trois": 3, "dos": 2, "tres": 3}


def totals(rfq: dict) -> tuple[float | None, float | None]:
    """(total kg, total m3) of an Rfq; m3 from the stated volume or else from the dimensions."""
    pieces = rfq["pieces"]
    kg = sum(p["count"] * p["weight_kg"] for p in pieces) if pieces and all(p["weight_kg"] for p in pieces) else None
    m3 = rfq["volume_m3"]
    if m3 is None and pieces and all(p["length_cm"] and p["width_cm"] and p["height_cm"] for p in pieces):
        m3 = sum(p["count"] * p["length_cm"] * p["width_cm"] * p["height_cm"] for p in pieces) / 1e6
    return kg, m3


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
    kg, m3 = totals(rfq)
    if kg and m3 and not DENSITY_KG_M3[0] <= kg / m3 <= DENSITY_KG_M3[1]:
        found.append(f"implausible density: {kg:g} kg in {m3:g} m3")
    lines = [p["count"] * p["weight_kg"] for p in rfq["pieces"] if p["weight_kg"]]
    if len(lines) >= 3 and any(abs(2 * line - sum(lines)) <= 0.005 * sum(lines) for line in lines):
        found.append("one piece line is the total of the others (counted twice)")
    return found


def _mail_numbers(text: str) -> set[float]:
    """Every number in the mail, read both ways where the separator is ambiguous (1.233 / 1,150 / 6,8)."""
    found = set()
    for token in _MAIL_NUMBER.findall(text):
        token = token.replace(" ", "").replace(" ", "")
        plain = re.sub(r"[.,](?=\d{3}\b)", "", token)  # thousands separators: 1.233 / 1,150 / 1.250,5
        for candidate in (token.replace(",", "."), plain.replace(",", "."), token.replace(",", "")):
            try:
                found.add(round(float(candidate), 4))
            except ValueError:
                pass
    return found


def ungrounded(raw: dict, mail: dict) -> list[str]:
    """Numbers the model returned that the mail doesn't contain (it converted or invented them), and a ready date
    before the mail. Free: plain code on the mail text."""
    text = f"{mail.get('subject', '')}\n{mail.get('body', '')}"
    known = _mail_numbers(text) | {float(n) for w, n in _WORDS.items() if re.search(rf"\b{w}\b", text, re.I)}
    values = [raw.get("volume")] + [v for p in raw["pieces"] for v in
                                    (p["weight"], p["length"], p["width"], p["height"], p.get("volume"))]
    values += [p["count"] for p in raw["pieces"] if p["count"] and p["count"] > 1]
    found = [f"{v:g} is not in the mail" for v in values if v is not None and round(float(v), 4) not in known]
    sent = (mail.get("received_at") or "")[:10]
    if raw.get("ready_date") and sent and raw["ready_date"] < sent:
        found.append(f"ready date {raw['ready_date']} is before the mail ({sent})")
    return found


def _problems(raw: dict, rfq: dict, missing: list[str], mail: dict) -> list[str]:
    return [f"missing {m}" for m in missing] + doubts(rfq) + ungrounded(raw, mail)


def read_request(mail: dict) -> dict:
    """Orchestrator: cheap actor first; escalate to the stronger actor only if the result is incomplete or implausible.

    A reading that still gives an impossible density after the escalation goes to a person: a quote priced from a
    misread weight or volume is rejected anyway, a person can still win it.
    Returns {rfq, missing, cost, model, escalated: reasons or None}.
    """
    raw, cost = extract(mail)
    rfq, missing = to_rfq(raw)
    reasons = _problems(raw, rfq, missing, mail)
    if not reasons:
        return {"rfq": rfq, "missing": missing, "cost": cost, "model": llm.MODEL, "escalated": None}
    model = llm.MODEL
    try:
        raw2, cost2 = extract(mail, ESCALATION_MODEL)
    except Exception as error:  # the stronger actor failing must never cost us the cheap result
        reasons = reasons + [f"escalation failed: {type(error).__name__}"]
    else:
        cost += cost2
        rfq2, missing2 = to_rfq(raw2)
        if len(_problems(raw2, rfq2, missing2, mail)) <= len(reasons):  # not worse: trust the stronger reader
            rfq, missing, model = rfq2, missing2, ESCALATION_MODEL
    density = [d for d in doubts(rfq) if d.startswith("implausible density")]
    return {"rfq": rfq, "missing": missing + density, "cost": cost, "model": model, "escalated": reasons}


def _line_volume(p: dict) -> float | None:
    """A piece line's volume as written, for the whole line."""
    volume = p.get("volume")
    if volume is None:
        return None
    return volume if p.get("volume_is_total", True) else volume * (p["count"] or 1)


def _line_volumes(raw_pieces: list[dict], pieces: list[dict], to_m3: float) -> float | None:
    """The shipment's volume in m3 from its lines when at least one line gives a volume instead of dimensions.

    Per line: the volume written for it (times the count when it is per piece), else count × L × W × H. "Lot 1: 730 kg /
    1.68 cbm, Lot 2: 4 cartons each 110x110x52, Lot 3: 5 cases each 120x100x8" → 1.68 + 2.5168 + 0.48 = 4.68. None if
    a line has neither, or if no line gives a volume (then the backend uses the dimensions itself).
    """
    if not any(_line_volume(p) is not None for p in raw_pieces):
        return None
    total = 0.0
    for raw, piece in zip(raw_pieces, pieces):
        if (volume := _line_volume(raw)) is not None:
            total += volume * to_m3
        elif piece["length_cm"] and piece["width_cm"] and piece["height_cm"]:
            total += piece["count"] * piece["length_cm"] * piece["width_cm"] * piece["height_cm"] / 1e6
        else:
            return None
    return total


AREAS: dict[str, str] = {}  # normalised area name → zone, filled on first use
ALIASES = {"muenchen": "munich", "koeln": "cologne", "frankfurt": "frankfurt am main", "duesseldorf": "duesseldorf"}


def _plain(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return text


def city_zone(address: str | None) -> str | None:
    """Pickup zone from a city name when the address has no postcode ("our plant in Ingolstadt" → 85)."""
    if not address or not ZONES.exists():
        return None
    if not AREAS:
        with ZONES.open(newline="") as f:
            AREAS.update({_plain(row["area"]): row["zone"] for row in csv.DictReader(f)})
    text = _plain(address)
    for alias, area in ALIASES.items():
        text = re.sub(rf"\b{alias}\b", area, text)
    hits = [area for area in AREAS if re.search(rf"\b{re.escape(area)}\b", text)]
    return AREAS[max(hits, key=len)] if hits else None  # "munich south" beats "munich"


def to_rfq(raw: dict) -> tuple[dict, list[str]]:
    """Raw extraction → contract Rfq (cm, kg per piece, m3) and the list of fields we can't price without."""
    cm, kg, m3 = TO_CM[raw["dim_unit"]], TO_KG[raw["weight_unit"]], TO_M3[raw.get("volume_unit") or "m3"]
    pieces = []
    for p in raw["pieces"]:
        count = p["count"] or 1
        weight = p["weight"] / count if p["weight"] is not None and p["weight_is_total"] else p["weight"]
        pieces.append({
            "count": count,
            "length_cm": round(p["length"] * cm, 1) if p["length"] is not None else None,
            "width_cm": round(p["width"] * cm, 1) if p["width"] is not None else None,
            "height_cm": round(p["height"] * cm, 1) if p["height"] is not None else None,
            "weight_kg": round(weight * kg, 6) if weight is not None else None,  # 1228 kg / 12 must add up to 1228 again
        })
    volume = raw["volume"] * m3 if raw["volume"] is not None else _line_volumes(raw["pieces"], pieces, m3)
    pickup = None
    if raw["pickup_address"]:
        pickup = {"address": raw["pickup_address"], "zone": None}
        if not pickup_zone(pickup):
            pickup["zone"] = city_zone(raw["pickup_address"])  # no postcode: the city tells the zone
    rfq = {
        "origin": raw["origin"],
        "destination": raw["destination"],
        "ask": raw["ask"] or "cheapest",
        "pickup": pickup,
        "ready_date": raw["ready_date"],
        "pieces": pieces,
        "volume_m3": round(volume, 4) if volume is not None else None,
        "commodity": raw["commodity"],
        "dangerous_goods": raw["dangerous_goods"],
        "customer_reference": raw["customer_reference"],
        "language": raw["language"],
    }
    notes = []
    for field in ("origin", "destination"):  # "Tokyo" read as HND, "New York" as NYC: same city, the airport we price
        rfq[field], note = priceable(rfq[field])
        if note:
            notes.append(f"{field} {note}")
    if notes:
        rfq["airport_note"] = "; ".join(notes)
    if rfq["pickup"] and (airport := zone_airport(rfq["pickup"])):
        rfq["origin"] = airport  # door-to-port flies from the pickup zone's airport (Bergisch Gladbach 51 → CGN)
    missing = [f for f in ("origin", "destination") if not rfq[f]]
    if not pieces or any(p["weight_kg"] is None for p in pieces):
        missing.append("weight")
    has_dims = pieces and all(p["length_cm"] and p["width_cm"] and p["height_cm"] for p in pieces)
    if not has_dims and rfq["volume_m3"] is None:
        missing.append("dimensions or volume")
    return rfq, missing
