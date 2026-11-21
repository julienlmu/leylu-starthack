"""Tracking agent: answers "where is it?" from tracking@ out of our own CRM. No LLM, no portal call (there is none).

5U's tracking questions often name no reference at all ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg,
ready on 2026-11-25"). Then the booked shipment is found by what the question repeats from its RFQ (tracking_match).
"""

import re

from inbox import reply_data
from booking_agent import is_booked
from templates import tracking_text, tracking_unknown_text
from tracking_match import best_match, is_date

# Booking references (BK-1A2B3C4D), our portal team reference (S-12), then anything that looks like a reference
# (PO-4711, AB123456).
REFERENCES = re.compile(r"\bBK-[A-Z0-9]{8}\b|\bS-\d+\b|\b[A-Z0-9]{2,}(?:[-/][A-Z0-9]+)+\b|\b[A-Z]{2,}\d{3,}\b")
BOOKING_REF = re.compile(r"\bBK-[A-Z0-9]{8}\b")
MAX_LOOKUPS = 5


def handle_tracking(mail: dict, box, api) -> None:
    text = f"{mail['subject']}\n{mail['body']}"
    candidates = [r for r in dict.fromkeys(REFERENCES.findall(text)) if not is_date(r)][:MAX_LOOKUPS]
    session = next((s for ref in candidates if (s := api.find(reference=ref))), None)
    # A quoted BK- number we don't know is someone else's booking: ask, don't guess from the shipment details.
    if (session is None or not is_booked(session)) and not BOOKING_REF.search(text):
        session = best_match(text, [s for s in api.booked_sessions() if is_booked(s)])
    if session is None or not is_booked(session):
        print(f"tracking question without a booked shipment: {candidates}")
        box.reply(mail, tracking_unknown_text())
        return
    answer = tracking_text(session)
    box.reply(mail, answer)
    api.event(session["id"], "tracking_answer", f"Tracking question answered ({mail['from']})", reply_data(mail, answer))
