"""Find the booked shipment a tracking question is about when it names no reference. No LLM, stdlib only.

5U's tracking questions describe the shipment the way the customer's RFQ did, e.g.
"Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, ready on 2026-11-25". So each booked session is scored
on what the question repeats from its RFQ: customer, pickup postcode or origin airport, destination, weight,
ready date. All questions seen on Sat 21 Nov (#923, #1212, #1447) follow that pattern and quote no reference.
Only a clear winner counts: a wrong shipment's status is worse than asking for the booking reference.
"""

import re

MIN_SCORE = 5  # e.g. destination + weight, or customer + destination + date
WEIGHTS = {"weight": 3, "customer": 2, "destination": 2, "postcode": 2, "ready_date": 2, "origin": 1}

_KG = re.compile(r"(\d{1,3}(?:[.,  ]\d{3})+|\d+(?:[.,]\d+)?)\s*(?:kg|kilo)", re.I)
_POSTCODE = re.compile(r"\b\d{4,5}\b")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ANY_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def is_date(text: str) -> bool:
    """`2026-11-25` looks like a reference to the reference regex; it isn't one."""
    return bool(_ISO_DATE.match(text))


def _number(raw: str) -> float:
    """1233 · 1,233 · 1.233 · 1 233 → 1233.0; 1233,5 / 1233.5 → 1233.5."""
    if re.fullmatch(r"\d{1,3}(?:[.,  ]\d{3})+", raw):
        return float(re.sub(r"[.,  ]", "", raw))
    return float(raw.replace(",", "."))


def _weights_in(text: str) -> list[float]:
    return [_number(m.group(1)) for m in _KG.finditer(text)]


def _gross_kg(rfq: dict) -> float:
    return sum((p.get("count") or 1) * (p.get("weight_kg") or 0) for p in rfq.get("pieces") or [])


def _customer_words(customer: str) -> set[str]:
    """`sonnberg-roesterei@hackloop.mail` → {"sonnberg", "roesterei"}: the parts a person would also write."""
    local = customer.split("@")[0].lower()
    return {w for w in re.split(r"[^a-z0-9äöüß]+", local) if len(w) >= 4}


def signals(text: str, session: dict) -> dict[str, bool]:
    """Which parts of the session's RFQ the question repeats."""
    rfq = session.get("rfq") if isinstance(session.get("rfq"), dict) else {}
    low = text.lower()
    words = set(re.findall(r"[a-z0-9äöüß]+", low))
    # The question may quote the RFQ's gross weight or the booked weight (5U's booking record): accept either.
    known = [w for w in (_gross_kg(rfq), (session.get("booking") or {}).get("weight_kg"),
                         (session.get("quote") or {}).get("chargeable_weight_kg")) if w]
    address = ((rfq.get("pickup") or {}).get("address") or "")
    postcodes = set(_POSTCODE.findall(address))
    destination, origin = (rfq.get("destination") or "").lower(), (rfq.get("origin") or "").lower()
    return {
        "weight": any(abs(w - k) <= max(1.0, k * 0.005) for w in _weights_in(text) for k in known),
        "customer": bool(_customer_words(session.get("customer") or "") & words),
        "destination": bool(destination) and destination in words,
        "postcode": bool(postcodes & set(_POSTCODE.findall(text))),
        "ready_date": bool(rfq.get("ready_date")) and str(rfq["ready_date"]) in text,
        "origin": bool(origin) and origin in words,
    }


def score(text: str, session: dict) -> int:
    """Points for what the question repeats; 0 when it contradicts the shipment or names no weight or date of it."""
    hits = signals(text, session)
    rfq = session.get("rfq") if isinstance(session.get("rfq"), dict) else {}
    other_date = rfq.get("ready_date") and _ANY_ISO_DATE.search(text) and not hits["ready_date"]
    other_weight = _weights_in(text) and not hits["weight"]
    if other_date or other_weight or not (hits["weight"] or hits["ready_date"]):
        return 0  # e.g. the same customer's other shipment: a wrong status is worse than asking for the reference
    return sum(WEIGHTS[name] for name, hit in hits.items() if hit)


def best_match(text: str, sessions: list[dict]) -> dict | None:
    """The booked session the question describes, or None when no session clearly fits."""
    ranked = sorted(((score(text, s), s) for s in sessions if s.get("booking")), key=lambda x: x[0], reverse=True)
    if not ranked or ranked[0][0] < MIN_SCORE:
        return None
    if len(ranked) > 1 and ranked[1][0] == ranked[0][0]:
        return None  # two shipments fit equally well: don't guess
    return ranked[0][1]
