"""Tracking agent: answers "where is it?" from tracking@ out of our own CRM. No LLM, no portal call (there is none)."""

import re

from inbox import reply_data
from templates import tracking_text, tracking_unknown_text

# Booking references (BK-1A2B3C4D) first, then anything that looks like a reference (PO-4711, AB123456).
REFERENCES = re.compile(r"\bBK-[A-Z0-9]{8}\b|\b[A-Z0-9]{2,}(?:[-/][A-Z0-9]+)+\b|\b[A-Z]{2,}\d{3,}\b")
MAX_LOOKUPS = 5


def handle_tracking(mail: dict, box, api) -> None:
    candidates = list(dict.fromkeys(REFERENCES.findall(f"{mail['subject']}\n{mail['body']}")))[:MAX_LOOKUPS]
    session = next((s for ref in candidates if (s := api.find(reference=ref))), None)
    if session is None or not session.get("booking"):
        print(f"tracking question without a booked shipment: {candidates}")
        box.reply(mail, tracking_unknown_text())
        return
    text = tracking_text(session)
    box.reply(mail, text)
    api.event(session["id"], "tracking_answer", f"Tracking question answered ({mail['from']})", reply_data(mail, text))
