"""Tracking agent: answers "where is it?" from tracking@ out of our own CRM. No LLM, no portal call (there is none).

5U's tracking questions often name no reference at all ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg,
ready on 2026-11-25"). Then the booked shipment is found by what the question repeats from its RFQ (tracking_match).
"""

import re

from inbox import reply_data
from templates import tracking_text, tracking_unknown_text
from tracking_match import best_match, is_date

# Booking references (BK-1A2B3C4D) first, then anything that looks like a reference (PO-4711, AB123456).
REFERENCES = re.compile(r"\bBK-[A-Z0-9]{8}\b|\b[A-Z0-9]{2,}(?:[-/][A-Z0-9]+)+\b|\b[A-Z]{2,}\d{3,}\b")
MAX_LOOKUPS = 5


def handle_tracking(mail: dict, box, api) -> None:
    text = f"{mail['subject']}\n{mail['body']}"
    candidates = [r for r in dict.fromkeys(REFERENCES.findall(text)) if not is_date(r)][:MAX_LOOKUPS]
    session = next((s for ref in candidates if (s := api.find(reference=ref))), None)
    if session is None or not session.get("booking"):
        session = best_match(text, api.booked_sessions())
    if session is None or not session.get("booking"):
        print(f"tracking question without a booked shipment: {candidates}")
        box.reply(mail, tracking_unknown_text())
        return
    answer = tracking_text(session)
    box.reply(mail, answer)
    api.event(session["id"], "tracking_answer", f"Tracking question answered ({mail['from']})", reply_data(mail, answer))
