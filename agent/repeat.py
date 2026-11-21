"""SAME_AS_LAST: "same as last time", "wie letztes Mal, aber 3 Paletten", "repeat order": the fields this mail leaves
open (route, pickup, pieces, volume, goods) come from the customer's newest earlier request in our CRM, never from
another customer. What the new mail does say wins; a new piece count keeps the old per-piece weight and size. Rules
only, no LLM. Nothing earlier from this sender → the mail is read as it is (missing fields as before). off = as before.
"""

import os
import re
from email.utils import parseaddr

SAME_AS_LAST = os.environ.get("SAME_AS_LAST", "on").lower() != "off"
SAME = re.compile(
    r"\b(?:same|identical|similar)\s+(?:\w+\s+){0,2}?(?:as|like|to)\s+(?:the\s+|our\s+|my\s+)?(?:last|previous|earlier|"
    r"prior)\b|\b(?:like|as)\s+(?:the\s+)?last\s+(?:time|week|month|one|shipment|order)\b|\brepeat\s+(?:order|shipment|"
    r"booking)\b|\bwie\s+(?:beim\s+)?(?:letzte[sn]?|vorige[sn]?|das\s+letzte)\s+mal\b|\bwie\s+letzte\s+woche\b|"
    r"\b(?:gleiche|selbe|dieselbe|identische)\w*\s+(?:\w+\s+){0,2}?wie\s+(?:beim\s+)?(?:letzte|vorige|zuletzt)|"
    r"\bcomme\s+la\s+derni[eè]re\s+fois\b|\bcomo\s+la\s+[uú]ltima\s+vez\b|\bcome\s+l['’]ultima\s+volta\b", re.I)


def asks_same(mail: dict) -> bool:
    return SAME_AS_LAST and bool(SAME.search(f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"))


def previous_request(api, mail: dict, session_id: int) -> dict | None:
    """The newest earlier session of this sender with a priceable request."""
    sender = parseaddr(mail.get("from") or "")[1].lower()
    try:
        sessions = api.sessions()
    except Exception:
        return None
    for s in sorted(sessions, key=lambda s: s.get("id") or 0, reverse=True):
        rfq = s.get("rfq") or {}
        if s.get("id") != session_id and parseaddr(s.get("customer") or "")[1].lower() == sender \
                and rfq.get("origin") and rfq.get("destination") and rfq.get("pieces") \
                and all(p.get("weight_kg") for p in rfq["pieces"]):
            return s
    return None


def _no_weight(pieces) -> bool:
    return not pieces or any(p.get("weight_kg") is None for p in pieces)


def fill(rfq: dict, missing: list[str], old: dict) -> tuple[dict, list[str], list[str]]:
    """(rfq, missing, what was taken) with the open fields filled from the old request."""
    rfq, taken = dict(rfq), []
    for field in ("origin", "destination"):
        if not rfq.get(field) and old.get(field):
            rfq[field] = old[field]
            taken.append(f"{field} {old[field]}")
            if field == "origin" and not rfq.get("pickup") and old.get("pickup"):
                rfq["pickup"] = dict(old["pickup"])
                taken.append("pickup")
    if _no_weight(rfq.get("pieces")) and old.get("pieces"):
        new_count = sum(int(p.get("count") or 0) for p in rfq.get("pieces") or [])
        old_count = sum(int(p.get("count") or 0) for p in old["pieces"])
        if len(old["pieces"]) == 1 and new_count and new_count != old_count:  # "same as last time, but 3 pallets"
            rfq["pieces"] = [{**old["pieces"][0], "count": new_count}]
            if old.get("volume_m3") and not rfq.get("volume_m3") and old_count:
                rfq["volume_m3"] = round(old["volume_m3"] * new_count / old_count, 4)
            taken.append(f"per-piece weight and size for {new_count} pieces")
        else:
            rfq["pieces"] = [dict(p) for p in old["pieces"]]
            if not rfq.get("volume_m3") and old.get("volume_m3"):
                rfq["volume_m3"] = old["volume_m3"]
            taken.append("pieces, weight and size")
    elif "dimensions or volume" in missing and old.get("volume_m3") and not rfq.get("volume_m3"):
        rfq["volume_m3"] = old["volume_m3"]
        taken.append("volume")
    for field in ("commodity", "dangerous_goods"):
        if rfq.get(field) in (None, "") and old.get(field) not in (None, ""):
            rfq[field] = old[field]
    has_dims = rfq.get("pieces") and all(p.get("length_cm") and p.get("width_cm") and p.get("height_cm")
                                         for p in rfq["pieces"])
    still = [m for m in missing if not (
        (m == "origin" and rfq.get("origin")) or (m == "destination" and rfq.get("destination")) or
        (m == "weight" and not _no_weight(rfq.get("pieces"))) or
        (m == "dimensions or volume" and (has_dims or rfq.get("volume_m3"))))]
    return rfq, still, taken
