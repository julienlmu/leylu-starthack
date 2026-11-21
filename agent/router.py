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
    if not known_thread and SPAM_FILTER and is_spam(mail):
        return "spam"  # 21:09: 5U sends spam; no reply, no LLM, no person
    return "customer_reply" if known_thread else "rfq"


SPAM_FILTER = __import__("os").environ.get("SPAM_FILTER", "on").lower() != "off"
# Any of these and it is treated as an RFQ: dropping a real RFQ loses the round, a spam answer costs little.
SHIPMENT_SIGNAL = re.compile(
    r"\d[\d.,]*\s?(?:kg|kgs|kilo\w*|lbs?|pounds?|t|tons?|tonnes?|cbm|m3|m³|cm|mm|pcs|pieces?|pallets?|crates?|boxes|"
    r"box|cartons?|colli|packst\w*|kisten?|paletten?)\b|\d+\s?[x×]\s?\d+|\b[A-Z]{3}\s?(?:-|–|to|nach|→)\s?[A-Z]{3}\b|"
    r"\b(?:quote|quotation|rate|rates|rfq|freight|shipment|shipping|cargo|air ?freight|pickup|pick-up|airport|"
    r"sendung|angebot|fracht|luftfracht|abholung|flughafen|ready (?:on|for)|dangerous goods|un ?\d{4})\b", re.I)
STRONG_SIGNAL = re.compile(
    r"\d[\d.,]*\s?(?:kg|kgs|kilo\w*|lbs?|pounds?|t|tons?|tonnes?|cbm|m3|m³|cm|mm|pcs|pieces?|pallets?|crates?|boxes|"
    r"box|cartons?|colli|packst\w*|kisten?|paletten?)\b|\d+\s?[x×]\s?\d+|\b[A-Z]{3}\s?(?:-|–|to|nach|→)\s?[A-Z]{3}\b|"
    r"\bun ?\d{4}\b|\b(?:ready (?:on|for)|pickup (?:on|from|at)|abholung)\b", re.I)
SPAM_WORDS = re.compile(
    r"\b(unsubscribe|newsletter|webinar|limited[- ]time|special offer|% off|discount code|promo|click here|"
    r"buy now|act now|winner|won a|lottery|prize|gift card|crypto|bitcoin|investment opportunity|seo|"
    r"backlinks?|out of office|out-of-office|automatic reply|auto-?reply|abwesenheit\w*|nicht im büro|"
    r"verify your account|account (?:suspended|locked)|reset your password|invoice overdue|wire transfer|"
    r"bank details|dear friend|congratulations|demo|free trial|book (?:a |15 |30 )?(?:minutes?|call|meeting|slot)|"
    r"schedule a (?:call|meeting|demo)|our (?:software|platform|solution|tool|product)|case study|"
    r"account executive|sales (?:team|rep\w*)|partnership opportunity|lead generation)\b", re.I)


def is_spam(mail: dict) -> bool:
    """Spam only with no shipment signal at all (weight, dims, IATA pair, quote words, attachment) and a spam word."""
    if mail.get("attachments"):
        return False
    text = f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"
    spam = {m.group(0).lower() for m in SPAM_WORDS.finditer(text)}
    if not spam or STRONG_SIGNAL.search(text):
        return False
    # only quote/RFQ words, no weight or route: a sales pitch "we answer every RFQ in 60 s" (R55) needs 2+ spam words
    return not SHIPMENT_SIGNAL.search(text) or len(spam) >= 2
