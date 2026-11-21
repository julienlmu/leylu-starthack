"""Carrier bids: read the replies and hand them to the RFQ that is waiting for them.

Replies are parsed with regexes first (free). Only a reply the regexes can't read costs a tiny LLM call.
"""

import os
import queue
import re
import threading

import llm
from inbox import latest_text

# Carriers write "EUR 1,450", "1450 eur", "980 Euro", "1.450 euros": every spelling is money (a missed one becomes an
# LLM call at best, or a bid mistaken for a question at worst).
_CUR = r"\b(?:EUR(?:OS?)?|USD|GBP|CHF)\b|€|\$"
# Swiss thousands apostrophe: CHF 2'450.00 (SWISS_NUMBERS=off: the old reading, which saw CHF 2.00)
SWISS_NUMBERS = os.environ.get("SWISS_NUMBERS", "on").lower() != "off"
_AMOUNT = r"\d(?:[\d.,]|['\u2019](?=\d{3}))*" if SWISS_NUMBERS else r"\d[\d.,]*"
MONEY_BEFORE = re.compile(rf"({_CUR})\s?({_AMOUNT})", re.I)
MONEY_AFTER = re.compile(rf"({_AMOUNT})\s?({_CUR})", re.I)
SYMBOLS = {"€": "EUR", "$": "USD", "EURO": "EUR", "EUROS": "EUR"}
TOTAL_WORDS = re.compile(r"total|all[- ]?in|gesamt|price|preis|prix|offer|angebot", re.I)
TRANSIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(days?|d\b|tagen?|tage|jours?|días|hours?|hrs?|h\b|stunden|std)", re.I)
TRANSIT_LINE = re.compile(r"transit|delivery|flight|laufzeit|lieferzeit", re.I)
VALIDITY = re.compile(r"valid|g[üu]ltig", re.I)
HOURS = ("h", "hour", "hours", "hr", "hrs", "stunden", "std")
RATE_ID = re.compile(r"rate[\s_-]*id\s*[:#]?\s*([A-Za-z0-9][\w/-]{2,})", re.I)

_NUM = {"type": ["number", "null"]}
_STR = {"type": ["string", "null"]}
BID_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["total", "currency", "transit_days", "rate_id"],
    "properties": {"total": _NUM, "currency": _STR, "transit_days": _NUM, "rate_id": _STR},
}
BID_PROMPT = ("Extract the carrier's offer from the email: all-in total, ISO currency code, "
              "transit time in days, rate ID. Null for anything not offered. If it offers several totals "
              "(for example at different weight breaks), take the cheapest one with its own rate ID.")


def to_number(text: str) -> float | None:
    """'1,234.50', '1.234,50', '1234,5', '1.234' and (Swiss) "2'450.00" all become numbers."""
    s = text.rstrip(".,")
    if SWISS_NUMBERS:
        s = re.sub(r"['\u2019](?=\d{3})", "", s)
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if decimal == "," else ",", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "") if len(s.rpartition(",")[2]) == 3 else s.replace(",", ".")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.rpartition(".")[2]) == 3):
        s = s.replace(".", "")  # dots as thousands separators
    try:
        return float(s)
    except ValueError:
        return None


def _money(text: str) -> set[tuple[float, str]]:
    found = [(amount, cur) for cur, amount in MONEY_BEFORE.findall(text)] + MONEY_AFTER.findall(text)
    return {(value, SYMBOLS.get(cur.upper(), cur.upper())) for amount, cur in found
            if (value := to_number(amount)) is not None}


# What an amount is, from the words right around it on its own line.
PER_KG = re.compile(r"^\s*(?:/\s*|per\s+|pro\s+|je\s+|par\s+|por\s+)(?:chargeable\s+|billed\s+|chg\.?\s*)?(?:kg|kilo)",
                    re.I)
ALL_IN_BEFORE = re.compile(r"(?:total|all[- ]?in|gesamt|insgesamt|tout compris|todo incluido)\w*(?:\s+\w+){0,2}\)?\s*"
                           r"[:=]?\s*$", re.I)
ALL_IN_AFTER = re.compile(r"^\W{0,3}(?:all[- ]?in|in total|total|gesamt|insgesamt|tout compris|flat)\b", re.I)
MINIMUM = re.compile(r"\bmin(?:imum|\.)?(?:\s+charge)?\W{0,4}$|\bmindestens\W{0,4}$", re.I)
SURCHARGE = re.compile(r"fuel|security|surcharge|zuschlag|kerosin|treibstoff|sicherheit|screening|\bfsc\b|\bssc\b|"
                       r"handling|\bfees?\b|geb\u00fchr|\bplus\b|\+|excl|exclusive|excluding|zzgl|zuz\u00fcglich|"
                       r"additional|not included|on top|hors|en sus", re.I)
INCLUDED = re.compile(r"\b(?:incl|inkl|included|inclusive|enthalten|inclus)", re.I)
# An optional extra ("insurance optional EUR 120", "return leg on request") is not part of the price: adding it
# overprices the quote (too_high is rejected too), so such a reply goes to the LLM as before.
OPTIONAL = re.compile(r"\boptional|on request|upon request|if required|if needed|if desired|auf wunsch|"
                      r"wahlweise|falls gew\u00fcnscht|facultati", re.I)
PER_KG_BEFORE = re.compile(r"(?:/|\bper\s+)k(?:g|ilo)\w*\s*:?\s*$", re.I)  # "Rate per kg: EUR 2.10"
PER_UNIT = re.compile(r"^\s*(?:/|per\s)\s*[a-z]", re.I)
# Money code can't price: a surcharge or minimum without currency ("FSC 0.85/kg", "min 85"), a percentage, weight
# breaks ("+100 kg"), a sum ("= EUR 2.95/kg"). The LLM reads those, as before.
BARE = re.compile(r"(?:fuel|security|surcharge|\bfsc|\bssc|screening|handling|\bfees?|\bawb|zuschlag|"
                  r"\bmin(?:imum|\.)?)\W{0,4}(\d[\d.,]*)(?![\d.,]|\s*k(?:g|ilo))|(\d[\d.,]*)\s*(?:/|per\s+)\s*k(?:g|ilo)",
                  re.I)
UNCLEAR = re.compile(r"%|=|\bbreaks?\b|\+\s*\d[\d.,]*\s*kg|\d\s*\+\s*kg|\d\s*kg\s*\+", re.I)

def _amounts(text: str) -> list[dict]:
    """Every amount with its currency and what the words around it say: per kg, all-in total, minimum, surcharge."""
    found = []
    for pattern, cur_group, amount_group in ((MONEY_BEFORE, 1, 2), (MONEY_AFTER, 2, 1)):
        for m in pattern.finditer(text):
            value = to_number(m.group(amount_group))
            if value is None:
                continue
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            before = text[max(line_start, m.start() - 45):m.start()]
            after = text[m.end():line_end if line_end >= 0 else len(text)]
            found.append({"value": value, "currency": SYMBOLS.get(m.group(cur_group), m.group(cur_group)),
                          "start": m.start(), "end": m.end(), "per_unit": bool(PER_UNIT.match(after)),
                          "per_kg": bool(PER_KG.match(after) or PER_KG_BEFORE.search(before)),
                          "all_in": bool(ALL_IN_BEFORE.search(before[-25:]) or ALL_IN_AFTER.match(after)),
                          "minimum": bool(MINIMUM.search(before)), "extra": bool(SURCHARGE.search(before[-30:]))})
    unique: dict[int, dict] = {}  # "EUR 900 EUR" matches twice: keep one per position
    for amount in sorted(found, key=lambda a: a["start"]):
        if not any(abs(amount["start"] - start) <= 12 and amount["value"] == held["value"]
                   for start, held in unique.items()):
            unique[amount["start"]] = amount
    return list(unique.values())


def _unpriced(text: str, amounts: list[dict]) -> bool:
    """True when the reply holds money that code can't price (see BARE, UNCLEAR) or a per-hour/per-AWB amount."""
    return (bool(UNCLEAR.search(text)) or any(a["per_unit"] and not a["per_kg"] for a in amounts)
            or any(not any(a["start"] <= m.start(g) < a["end"] for a in amounts)
                   for m in BARE.finditer(text) for g in (1, 2) if m.group(g)))


def _code_total(text: str, chargeable_kg: float | None) -> tuple[float, str] | None:
    """The all-in total when a carrier writes it in another shape than our "Total: 1234.00 EUR".

    Only unambiguous shapes; anything else is None (the LLM reads it, as before):
    - one all-in amount: "EUR 1,980 all-in (EUR 1,700 + 280 fees)" → 1980
    - a base plus named extras: "air freight EUR 2,100 plus fuel EUR 310" → 2410, "Freight EUR 1,200 / Fuel EUR
      0.85/kg / Security EUR 0.15/kg" → 1200 + 1.00 × chargeable kg
    - one per-kg rate (+ minimum, + per-kg extras): "EUR 2.35/kg, min EUR 150" → max(150, 2.35 × kg)
    Anything marked included ("incl. fuel EUR 240") is None: adding it would count it twice. A per-kg amount is never
    a total on its own (2.35 as the total of a 1,000 kg shipment wins the pick and the quote is rejected too_low).
    """
    amounts = _amounts(text)
    if not amounts or len({a["currency"] for a in amounts}) != 1:
        return None
    currency = amounts[0]["currency"]
    flat = [a for a in amounts if not a["per_kg"] and not a["minimum"]]
    per_kg = [a for a in amounts if a["per_kg"]]
    if len({a["value"] for a in flat if a["all_in"]}) == 1:
        return next(a["value"] for a in flat if a["all_in"]), currency
    if INCLUDED.search(text) or OPTIONAL.search(text) or _unpriced(text, amounts):
        return None
    extras_kg = sum(a["value"] for a in per_kg if a["extra"])
    rates = [a for a in per_kg if not a["extra"]]
    if (extras_kg or rates) and chargeable_kg is None:
        return None
    if flat:
        base, *rest = flat
        if rates or (rest and not all(a["extra"] for a in rest)):
            return None  # a flat price next to a per-kg rate, or two prices: unclear
        return round(base["value"] + sum(a["value"] for a in rest) + extras_kg * (chargeable_kg or 0), 2), currency
    if len({a["value"] for a in rates}) != 1:
        return None
    minimum = max((a["value"] for a in amounts if a["minimum"] and not a["per_kg"]), default=0.0)
    return round(max(minimum, rates[0]["value"] * chargeable_kg) + extras_kg * chargeable_kg, 2), currency


def _plain_total(text: str) -> tuple[float, str] | None:
    """The one amount on the total/price lines, else the one amount in the reply (our own reply format)."""
    total_lines = "\n".join(line for line in text.splitlines() if TOTAL_WORDS.search(line))
    money = _money(total_lines)
    if len(money) != 1:
        money = _money(text)
    return next(iter(money)) if len(money) == 1 else None


# off = exactly the old reading (one amount or the LLM). On, code only steps in where the old reading gave up (the LLM
# then guessed) or took a per-kg rate for the total; every reply the old reading got right is read the same way.
BID_SHAPES = os.environ.get("BID_SHAPES", "on").lower() != "off"


def parse_bid(text: str, chargeable_kg: float | None = None) -> dict | None:
    """The single all-in amount (preferring lines that say total/price), transit days and rate ID, or None.

    chargeable_kg (the RFQ's billed weight) lets a per-kg offer or per-kg surcharges become an all-in total.
    """
    text = latest_text(text)  # a quoted copy of our request holds the example "Total: 1234.00 EUR"
    text = _without_extras(text)  # R68: "Not part of this offer: waiting time …, 45.00 EUR for each hour" became the bid
    found = _plain_total(text)
    amounts = _amounts(text)
    if BID_SHAPES and (found is None or any(a["per_kg"] and a["value"] == found[0] for a in amounts)
                       or _unpriced(text, amounts)):
        found = _code_total(text, chargeable_kg)
    if found is None:
        found = _bare_total(text)  # a PDF table: "Total 130.70" with "(EUR)" only in the column header
    if found is None:
        return None
    total, currency = found
    # "Transit: 1 day" beats "offer valid for 7 days": a validity is never the transit time
    after_word = [ln[w.start():] for ln in text.splitlines() if (w := TRANSIT_LINE.search(ln))]
    transit = next((m for ln in after_word if (m := TRANSIT.search(ln))), None) or next(
        (m for ln in text.splitlines() if not VALIDITY.search(ln) and (m := TRANSIT.search(ln))), None)
    transit_days = None
    if transit:
        value = to_number(transit.group(1))
        transit_days = value / 24 if transit.group(2).lower() in HOURS else value
    rate_id = RATE_ID.search(text)
    return {"total": total, "currency": currency, "transit_days": transit_days,
            "rate_id": rate_id.group(1) if rate_id else None}


DECLINE = re.compile(r"\b(do not|don't|does not|doesn't|cannot|can't|can not|unable to|not able to|won't|will not)\s+"
                     r"(serve|fly|offer|quote|cover|operate|handle|accept|provide)|\bnot serve|\bno capacity\b|"
                     r"\bregret\b|\bnot (available|possible)\b", re.I)


def read_bid(text: str, chargeable_kg: float | None = None) -> tuple[dict | None, float]:
    """Returns (bid or None, LLM cost in USD). Declines and replies without any amount never reach the LLM."""
    bid = parse_bid(text, chargeable_kg)
    if bid:
        return bid, 0.0
    latest = latest_text(text)
    # "We do not serve this lane": free, not $0.00004. A decline that still names a price ("not direct, but via AMS:
    # total EUR 2,450") goes to the LLM: a dropped bid can be the cheapest one, and missing it costs the quote.
    if (DECLINE.search(latest) and not _money(latest)) or not re.search(r"\d", latest):
        return None, 0.0
    data, cost = llm.chat_json("bid", BID_PROMPT, text, BID_SCHEMA)
    return (data if data["total"] is not None else None), cost


class BidBoard:
    """Connects bid-request threads to the RFQ session waiting for their replies (shared by worker threads)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._threads: dict[str, tuple[queue.Queue, dict]] = {}

    def watch(self, thread_id: str, replies: queue.Queue, carrier: dict) -> None:
        with self._lock:
            self._threads[thread_id] = (replies, carrier)

    def knows(self, thread_id: str) -> bool:
        with self._lock:
            return thread_id in self._threads

    def deliver(self, mail: dict) -> bool:
        """Hands a carrier reply to its RFQ. False if nobody waits for it any more (late bid)."""
        with self._lock:
            entry = self._threads.get(mail["thread_id"])
        if entry is None:
            return False
        replies, carrier = entry
        replies.put((carrier, mail))
        return True

    def forget(self, thread_ids: list[str]) -> None:
        with self._lock:
            for thread_id in thread_ids:
                self._threads.pop(thread_id, None)


INFO_ASK = re.compile(r"\b(to quote|before we can quote|in order to quote)\b[^\n]*\bneed\b|\bwe need\b[^\n]*:\s*$|"
                      r"\bplease (send|provide|let us know)\b", re.I | re.M)
INFO_ITEM = re.compile(r"^\s*[-*•]\s*(.+?)\s*$", re.M)


# A carrier that asks a question instead of quoting ("Is the cargo stackable?", "Can you confirm the commodity?") gets our
# details too, then we wait for its bid. Before: the question counted as "no usable offer" and the bid was lost.
CARRIER_QUESTIONS = os.environ.get("CARRIER_QUESTIONS", "on").lower() != "off"
QUESTION = re.compile(r"[^.!?\n]*\?", re.M)
POLITE = re.compile(r"\b(?:any(?:thing)? (?:other|else)|further questions|can we help|how can we help|"
                    r"would you like to book|shall we book)\b", re.I)


def info_request(text: str) -> list[str]:
    """What a carrier asks for before it can quote ("To quote we need: - the pickup postcode"), or [] for none."""
    latest = latest_text(text)
    # A reply with a price is a bid, even when it adds "please let us know if you'd like to book": never skip a bid.
    if _money(latest) or parse_bid(text):
        return []
    if INFO_ASK.search(latest):
        items = [i.strip().rstrip(".").lower() for i in INFO_ITEM.findall(latest)]
        return items or ["details"]
    # any number may be a price the regexes can't read ("980 Euro", "1,450 all-in"): read_bid decides, never skip a bid
    if not CARRIER_QUESTIONS or DECLINE.search(latest) or re.search(r"\d", latest):
        return []
    questions = [q.strip() for q in QUESTION.findall(latest) if not POLITE.search(q)]
    return [q.rstrip("?").lower() for q in questions if len(q) > 8][:3]


NOT_PART = re.compile(r"\b(not part of|not included|excluded|exclusive of|waiting time|demurrage|for each (?:hour|additional)|"
                      r"per (?:hour|additional)|each additional|on request|optional|nicht enthalten|wartezeit|je stunde|"
                      r"pro stunde)\b", re.I)


def _without_extras(text: str) -> str:
    """Lines about charges outside the offer (waiting time per hour, extras on request) and their wrapped tail."""
    out, skip_next = [], False
    for line in text.splitlines():
        if NOT_PART.search(line) and not TOTAL_WORD.search(line):  # "Total: 245.10 EUR (customs not included)" stays
            skip_next = not re.search(r"(?:\bEUR|\bUSD|€|\$)\s*$|\d\s*$", line) is None
            continue
        if skip_next and re.match(r"\s*(?:EUR|USD|€|\$)?\s*(?:for each|per|je|pro)\b", line, re.I):
            skip_next = False
            continue
        skip_next = False
        out.append(line)
    return "\n".join(out)


TOTAL_WORD = re.compile(r"\b(?:total|gesamt\w*|summe|all[- ]in)\b", re.I)
NOT_AN_OFFER = re.compile(r"\b(?:invoice|rechnung|proforma|amount due|payment due|terms and conditions|agb)\b", re.I)
BARE_TOTAL = re.compile(r"^\s*(?:grand\s+)?(?:total|gesamt\w*|summe)\b[^\d\n]{0,20}(\d[\d.,]*\d)\s*$", re.I | re.M)


def _bare_total(text: str) -> tuple[float, str] | None:
    """One 'Total <amount>' line and exactly one currency named in the document."""
    totals = BARE_TOTAL.findall(text)
    currencies = {c for c in ("EUR", "USD") if re.search(rf"\b{c}\b", text)} | ({"EUR"} if "€" in text else set())
    if len(totals) != 1 or len(currencies) != 1 or NOT_AN_OFFER.search(text):  # an invoice / T&C is never a bid
        return None
    value = to_number(totals[0])
    return (value, currencies.pop()) if value else None
