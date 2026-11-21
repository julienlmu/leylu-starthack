"""Spam and automatic replies, sorted out by rules before any LLM call (EMERGENCY_FIXES #11, docs/POSSIBLE_TRAPS.md).

5U now also sends spam: it must be ignored (no quote, no reply, no extraction call, which would lower the cost score).
A mail with any shipping facts is never spam: an RFQ with an "unsubscribe" footer still gets quoted.
`SPAM_FILTER=off` switches it off.
"""

import os
import re
from email.utils import parseaddr

ON = os.environ.get("SPAM_FILTER", "on").lower() != "off"

AUTO_SUBJECT = re.compile(r"^\s*(automatic reply|auto(matische)?[ -]?(reply|antwort)|auto:|out of (the )?office|"
                          r"abwesenheit\w*|undeliverable|delivery status notification|mail delivery (failed|system)|"
                          r"returned mail|r[ée]ponse automatique|absence)", re.I)
AUTO_SENDER = re.compile(r"^(mailer-daemon|postmaster|no-?reply|do-?not-?reply)@", re.I)

# Shipping facts in English and German (and the units every RFQ has). One hit = treat as a real request.
SHIPPING = re.compile(r"\b(freight|air ?freight|shipment|shipping|cargo|quote|quotation|rate|pick-?up|collection|"
                      r"pallets?|pieces|pcs|cartons?|gross weight|volume|cbm|kgs?|kilos?|airport|consignee|"
                      r"incoterms?|door[- ]to|fracht|luftfracht|sendung|angebot|abholung|paletten?|st[üu]ck|"
                      r"gewicht|flughafen)\b|\b\d+([.,]\d+)?\s?(kg|cbm|m3|m³|pcs)\b", re.I)
SPAM_WORDS = re.compile(r"unsubscribe|newsletter|click here|limited[- ]time|special offer|act now|winner|"
                        r"congratulations|lottery|prize|bitcoin|crypto|casino|viagra|seo |backlinks?|"
                        r"verify your (account|password|identity)|reset your password|update your (bank|payment) "
                        r"details|wire transfer|gift card|invoice attached|overdue invoice|dear (friend|beneficiary)",
                        re.I)
LINK = re.compile(r"https?://|www\.", re.I)


def is_auto_reply(mail: dict) -> bool:
    return bool(AUTO_SUBJECT.search(mail.get("subject") or "") or AUTO_SENDER.search(parseaddr(mail["from"])[1]))


def is_spam(mail: dict) -> bool:
    """No shipping facts at all, plus marketing/phishing words or links."""
    text = f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"
    if SHIPPING.search(text):
        return False
    return bool(SPAM_WORDS.search(text) or LINK.search(text))


def ignore(mail: dict) -> bool:
    return ON and (is_auto_reply(mail) or is_spam(mail))
