"""Carrier bids: read the replies and hand them to the RFQ that is waiting for them.

Replies are parsed with regexes first (free). Only a reply the regexes can't read costs a tiny LLM call.
"""

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


def parse_bid(text: str) -> dict | None:
    """The single all-in amount (preferring lines that say total/price), transit days and rate ID, or None."""
    text = latest_text(text)  # a quoted copy of our request holds the example "Total: 1234.00 EUR"
    total_lines = "\n".join(line for line in text.splitlines() if TOTAL_WORDS.search(line))
    money = _money(total_lines)
    if len(money) != 1:
        money = _money(text)
    if len(money) != 1:
        return None
    [(total, currency)] = money
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


def read_bid(text: str) -> tuple[dict | None, float]:
    """Returns (bid or None, LLM cost in USD). Declines and replies without any amount never reach the LLM."""
    bid = parse_bid(text)
    if bid:
        return bid, 0.0
    latest = latest_text(text)
    if DECLINE.search(latest) or not re.search(r"\d", latest):  # "We do not serve this lane": free, not $0.00004
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
