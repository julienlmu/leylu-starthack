"""Carrier bids: read the replies and hand them to the RFQ that is waiting for them.

Replies are parsed with regexes first (free). Only a reply the regexes can't read costs a tiny LLM call.
"""

import os
import queue
import re
import threading

import llm
from inbox import latest_text

MONEY_BEFORE = re.compile(r"(EUR|USD|GBP|CHF|€|\$)\s?(\d[\d.,]*)")
MONEY_AFTER = re.compile(r"(\d[\d.,]*)\s?(EUR|USD|GBP|CHF|€)")
SYMBOLS = {"€": "EUR", "$": "USD"}
TOTAL_WORDS = re.compile(r"total|all[- ]?in|gesamt|price|preis|prix|offer|angebot", re.I)
TRANSIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(days?|d\b|tagen?|tage|jours?|días|hours?|hrs?|h\b|stunden|std)", re.I)
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
              "transit time in days, rate ID. Null for anything not offered.")


def to_number(text: str) -> float | None:
    """'1,234.50', '1.234,50', '1234,5' and '1.234' all become numbers."""
    s = text.rstrip(".,")
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
    return {(value, SYMBOLS.get(cur, cur)) for amount, cur in found if (value := to_number(amount)) is not None}


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
EXCLUDED = re.compile(r"\bplus\b|\+|excl|exclusive of|excluding|zzgl|zuz\u00fcglich|additional|not included|on top|"
                      r"hors|en sus", re.I)


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
                          "start": m.start(), "per_kg": bool(PER_KG.match(after)),
                          "all_in": bool(ALL_IN_BEFORE.search(before[-25:]) or ALL_IN_AFTER.match(after)),
                          "minimum": bool(MINIMUM.search(before)), "extra": bool(SURCHARGE.search(before[-30:])),
                          "excluded": bool(EXCLUDED.search(text[line_start:m.start()]))
                          and not INCLUDED.search(after[:25])})
    unique: dict[int, dict] = {}  # "EUR 900 EUR" matches twice: keep one per position
    for amount in sorted(found, key=lambda a: a["start"]):
        if not any(abs(amount["start"] - start) <= 12 and amount["value"] == held["value"]
                   for start, held in unique.items()):
            unique[amount["start"]] = amount
    return list(unique.values())


def _code_total(text: str, chargeable_kg: float | None) -> tuple[float, str] | None:
    """The all-in total when a carrier writes it in another shape than our "Total: 1234.00 EUR":

    "EUR 1,850 plus fuel EUR 240" → 2090; "EUR 1,850 excl. fuel EUR 0.85/kg" → 1850 + 0.85 × chargeable kg;
    "EUR 2.35/kg, min EUR 150" → max(150, 2.35 × kg). A per-kg amount is never a total on its own (2.35 as the
    total of a 1,000 kg shipment wins the pick and gets the quote rejected too_low). None when it stays unclear.
    """
    amounts = _amounts(text)
    if not amounts or len({a["currency"] for a in amounts}) != 1:
        return None
    currency = amounts[0]["currency"]
    flat = [a for a in amounts if not a["per_kg"] and not a["minimum"]]
    per_kg = [a for a in amounts if a["per_kg"]]
    if len({a["value"] for a in flat if a["all_in"]}) == 1:
        return next(a["value"] for a in flat if a["all_in"]), currency  # "EUR 1,980 all-in (EUR 1,700 + 280)"
    extras_kg = sum(a["value"] for a in per_kg if a["extra"] and a["excluded"])
    if extras_kg and chargeable_kg is None:
        return None
    if flat:
        base, *rest = flat
        if rest and not all(a["extra"] for a in rest):
            return None
        return round(base["value"] + sum(a["value"] for a in rest) + extras_kg * (chargeable_kg or 0), 2), currency
    rates = [a for a in per_kg if not a["extra"]]
    if len({a["value"] for a in rates}) != 1 or chargeable_kg is None:
        return None
    minimum = max((a["value"] for a in amounts if a["minimum"] and not a["per_kg"]), default=0.0)
    surcharges = sum(a["value"] for a in per_kg if a["extra"])
    return round(max(minimum, rates[0]["value"] * chargeable_kg) + surcharges * chargeable_kg, 2), currency


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
    found = _plain_total(text)
    if BID_SHAPES and (found is None or any(a["per_kg"] and a["value"] == found[0] for a in _amounts(text))):
        found = _code_total(text, chargeable_kg)
    if found is None:
        return None
    total, currency = found
    transit = TRANSIT.search(text)
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


def info_request(text: str) -> list[str]:
    """What a carrier asks for before it can quote ("To quote we need: - the pickup postcode"), or [] for none."""
    latest = latest_text(text)
    # A reply with a price is a bid, even when it adds "please let us know if you'd like to book": never skip a bid.
    if _money(latest) or parse_bid(text) or not INFO_ASK.search(latest):
        return []
    items = [i.strip().rstrip(".").lower() for i in INFO_ITEM.findall(latest)]
    return items or ["details"]
