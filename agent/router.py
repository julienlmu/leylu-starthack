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
    if known_thread and SPAM_FILTER and is_auto_reply(mail, sender):
        # an out-of-office in our quote thread ("I will not be available") must not read as a decline, and one in a bid
        # thread is no carrier offer (it would end the bid wait or cost a bid-parser LLM call)
        return "other"
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
    r"box|cartons?|colli|packst\w*|kisten?|paletten?)\b|\d+\s?[x×]\s?\d+|(?-i:\b[A-Z]{3}\s?(?:-|–|to|nach|→)\s?[A-Z]{3}\b)|"
    # IATA pairs in capitals only ("you to win" was a route); "rate" only in a freight sense ("interest rate" isn't)
    r"\b(?:freight|air|shipping|best|your|spot)\s+rates?\b|\brates?\s+(?:for|from|to|ex)\b|"
    r"\b(?:quote|quotation|rfq|freight|shipment|shipping|cargo|air ?freight|pickup|pick-up|airport|"
    r"sendung|angebot|fracht|luftfracht|abholung|flughafen|ready (?:on|for)|dangerous goods|un ?\d{4})\b", re.I)
SPAM_WORDS = re.compile(
    r"\b(unsubscribe|newsletter|webinar|limited[- ]time|special offer|% off|discount code|promo|click here|"
    r"buy now|act now|winner|won a|lottery|prize|gift card|crypto|bitcoin|investment opportunity|seo|"
    r"backlinks?|out of office|out-of-office|automatic reply|auto-?reply|abwesenheit\w*|nicht im büro|"
    r"verify your account|account (?:suspended|locked)|reset your password|invoice overdue|wire transfer|"
    r"bank details|dear friend|congratulations)\b", re.I)


AUTO_SUBJECT = re.compile(r"^\s*(automatic reply|auto(?:matische)?[ -]?(?:reply|antwort)\b|auto:|out of (?:the )?office|"
                          r"abwesenheit\w*|undeliverable|delivery status notification|mail delivery (?:failed|system)|"
                          r"returned mail|r[ée]ponse automatique)", re.I)
AUTO_SENDER = re.compile(r"^(?:mailer-daemon|postmaster|no-?reply|do-?not-?reply)@", re.I)


def is_auto_reply(mail: dict, sender: str) -> bool:
    """Automatic replies by their subject or system sender only: a person's "I'm out of office tomorrow, please book"
    keeps its normal subject ("RE: …") and is read as usual."""
    return bool(AUTO_SUBJECT.search(mail.get("subject") or "") or AUTO_SENDER.search(sender))


PHISHING = re.compile(r"\b(invoice overdue|overdue invoice|wire transfer|bank details|verify your account|"
                      r"account (?:suspended|locked)|reset your password|gift card)\b", re.I)


RISKY_FILES = (".exe", ".zip", ".rar", ".js", ".html", ".htm", ".scr", ".iso", ".bat", ".cmd", ".vbs")
# V2 (Sat 21:50): 5U spam often carries soft freight words ("our air freight rates", "your shipment is on hold") but no
# actual request. Without an attachment, a mail is spam with a spam sign and neither a hard fact nor request wording.
HARD_FACT = re.compile(
    r"\d[\d.,]*\s?(?:kg|kgs|kilo\w*|lbs?|t|tons?|tonnes?|cbm|m3|m³|pcs|pieces?|pallets?|palettes?|paletten?|palets?|"
    r"palet|crates?|boxes|cartons?|colli|cajas?|koli|kisten?|packst\w*)\b|\d+\s?[x×]\s?\d+|"
    r"(?-i:\b[A-Z]{3}\s?(?:-|–|to|nach|→)\s?[A-Z]{3}\b)|"
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|zwei|drei|vier|fünf|deux|trois|dos|tres)\s+"
    r"(?:pallets?|paletten?|palettes?|pieces?|boxes|cartons?|crates?|tons?|tonnes?)\b|"
    r"\b(?:packing ?list|packing spec\w*|shipper'?s letter|sli|commercial invoice|proforma)\b", re.I)
REQUEST = re.compile(
    r"\b(?:please|pls|kindly|could you|can you|would you|we need|we'd like|we would like|i need|we require|send us|"
    r"send me|requesting|request for)\b(?:\W+\w+){0,5}?\W+(?:quote|quotation|offer|price|rate|rates|cost|pricing)\b|"
    r"\brfq\b|\b(?:bitte um|benötigen|brauchen|anfrage)\b.{0,40}\b(?:angebot|preis)|\bangebot\b|\bdevis\b|\bcotation\b|"
    r"\bcotizaci[oó]n\b|\bpresupuesto\b|\bpreventivo\b|\bquotazione\b|\bofferte\b|\bteklif\w*|\bfiyat\w*", re.I)
SPAM_V2 = re.compile(
    r"\b(?:special offer|exclusive offer|limited[- ]time|book now|buy now|order now|act now|click here|save \d+\s?%|"
    r"\d+\s?% off|free quote today|unsubscribe|newsletter|webinar|gewonnen|gewinn\w*|glückwunsch|jetzt klicken|abmelden|"
    r"rabatt|félicitations|cliquez|désabonner|vous avez gagné|felicidades|haga clic|darse de baja|premio|ganador|"
    r"congratulazioni|clicca qui|hai vinto|tebrikler|kazandınız|tıklayın|customs fee|held at customs|"
    r"parcel (?:is )?(?:held|on hold)|could not deliver|delivery failed|failed delivery|confirm your address|"
    r"pay (?:the )?[\d.,]+\s?(?:eur|usd|€|\$)?\s?fee|inheritance|next of kin|beneficiary|trusted partner|"
    r"million (?:usd|dollars|euros?)|god bless|business proposal|book a demo|schedule a (?:call|demo)|"
    r"partnership proposal|marketing services|apply for a job|job application|my cv|curriculum vitae|resume attached|"
    r"bewerbung|lebenslauf|you have been invited|invitation:|google meet|zoom meeting|teams meeting)", re.I)
LINK_ONLY = re.compile(r"https?://|www\.", re.I)


def is_spam(mail: dict) -> bool:
    """Spam only with no shipment signal at all (weight, dims, IATA pair, quote words, attachment) and a spam word."""
    text = f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"
    names = [str(a.get("filename") or "").lower() for a in mail.get("attachments") or [] if isinstance(a, dict)]
    if mail.get("attachments") and not any(n.endswith(RISKY_FILES) for n in names):
        return False  # a packing list or inquiry PDF always protects: dropping a real RFQ loses the round (review)
    if names and not PHISHING.search(text):
        return False
    if is_auto_reply(mail, parseaddr(mail.get("from") or "")[1]):  # an out-of-office/bounce from an unknown thread
        return True
    if SPAM_WORDS.search(text) and not SHIPMENT_SIGNAL.search(text):  # the #140 rule
        return True
    if HARD_FACT.search(text) or REQUEST.search(text):  # an actual request: never spam
        return False
    if SPAM_V2.search(text):  # V2: a spam sign and nothing that asks us for anything
        return True
    body = mail.get("body") or ""
    words = re.sub(r"https?://\S+|www\.\S+", " ", body).split()
    return not mail.get("attachments") and bool(LINK_ONLY.search(body)) and len(words) < 3  # a link and nothing else
