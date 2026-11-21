"""Tracking agent: answers "where is it?" from tracking@ out of our own CRM. No LLM, no portal call (there is none)."""

import re

from inbox import reply_data
from templates import tracking_text, tracking_unknown_text

# Booking references (BK-1A2B3C4D) first, then anything that looks like a reference (PO-4711, AB123456).
REFERENCES = re.compile(r"\bBK-[A-Z0-9]{8}\b|\b[A-Z0-9]{2,}(?:[-/][A-Z0-9]+)+\b|\b[A-Z]{2,}\d{3,}\b")
MAX_LOOKUPS = 5
POSTCODE = re.compile(r"\b\d{5}\b")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
MIN_SCORE = 5


def handle_tracking(mail: dict, box, api) -> None:
    text = f"{mail['subject']}\n{mail['body']}"
    candidates = list(dict.fromkeys(REFERENCES.findall(text)))[:MAX_LOOKUPS]
    session = next((s for ref in candidates if (s := api.find(reference=ref))), None)
    if session is None or not session.get("booking"):
        session = match_shipment(text, api.sessions(stage="booked"))  # 5U describes the shipment instead
    if session is None or not session.get("booking"):
        print(f"tracking question without a booked shipment: {candidates}")
        box.reply(mail, tracking_unknown_text())
        return
    text = tracking_text(session)
    box.reply(mail, text)
    api.event(session["id"], "tracking_answer", f"Tracking question answered ({mail['from']})", reply_data(mail, text))


def match_shipment(text: str, sessions: list[dict]) -> dict | None:
    """The booked session the mail describes: "Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, ready on 2026-11-25".

    Points per matching detail (pickup postcode 3, total kg 3, destination 2, ready date 2, company 2); the best
    session wins if it has at least MIN_SCORE and no other session ties with it.
    """
    lowered = text.lower()
    postcodes = set(POSTCODE.findall(text))
    numbers = [float(n.replace(",", ".")) for n in NUMBER.findall(text)]
    scored = []
    for s in sessions:
        rfq = s.get("rfq") if isinstance(s.get("rfq"), dict) else {}
        if not s.get("booking"):
            continue
        score = 0
        address = ((rfq.get("pickup") or {}).get("address") or "")
        if postcodes & set(POSTCODE.findall(address)):
            score += 3
        kg = sum((p.get("count") or 1) * (p.get("weight_kg") or 0) for p in rfq.get("pieces") or [])
        if kg and any(abs(n - kg) <= max(1.0, kg * 0.01) for n in numbers):
            score += 3
        if rfq.get("destination") and re.search(rf"\b{rfq['destination']}\b", text):
            score += 2
        if rfq.get("ready_date") and rfq["ready_date"] in text:
            score += 2
        domain = (s.get("customer") or "").split("@")[0].split("-")[0].lower()
        if len(domain) >= 4 and domain in lowered:
            score += 2
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < MIN_SCORE or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None
    return scored[0][1]
