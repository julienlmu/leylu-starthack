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
MONEY_BEFORE = re.compile(rf"({_CUR})\s?(\d[\d.,]*)", re.I)
MONEY_AFTER = re.compile(rf"(\d[\d.,]*)\s?({_CUR})", re.I)
SYMBOLS = {"€": "EUR", "$": "USD", "EURO": "EUR", "EUROS": "EUR"}
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
    return {(value, SYMBOLS.get(cur.upper(), cur.upper())) for amount, cur in found
            if (value := to_number(amount)) is not None}


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
