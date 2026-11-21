"""Rules-first router: sorts every mail by sender, thread and attachments, without an LLM call."""

import re
from email.utils import parseaddr

TRACKING = "tracking@hackloop.mail"
RATEDESK = "ratedesk@hackloop.mail"
# Start-kit tariffs come as xlsx, pdf, docx, txt and even a scanned image; the backend refuses what it can't read.
SHEET_EXTENSIONS = (".xlsx", ".xls", ".csv", ".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png")
CONFIRMED = re.compile(r"\bBooking\s+(BK-[A-Z0-9]{8})\s+confirmed", re.I)  # the airline's mail after a booking


def route(mail: dict, carriers: set[str], known_thread: bool) -> str:
    """Returns one of: tracking, ratedesk, booking_confirmed, carrier_bid, tariff, other, customer_reply, rfq.

    carriers: lower-case addresses from the start-kit carrier list.
    known_thread: mail["thread_id"] belongs to one of our sessions (a customer thread or a bid request we sent).
    """
    sender = parseaddr(mail["from"])[1].lower()
    if sender == TRACKING:
        return "tracking"
    if sender == RATEDESK:
        return "ratedesk"
    if CONFIRMED.search(mail.get("subject", "")):
        return "booking_confirmed"
    if sender in carriers:
        if known_thread:
            return "carrier_bid"
        has_sheet = any(a["filename"].lower().endswith(SHEET_EXTENSIONS) for a in mail.get("attachments", []))
        return "tariff" if has_sheet else "other"
    # Everyone else is a customer: a known thread is a reply to our quote (acceptance or question).
    return "customer_reply" if known_thread else "rfq"
