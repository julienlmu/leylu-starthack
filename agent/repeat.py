""""Same as our last order": a repeat request fills what the mail leaves out from the sender's previous request in the CRM.

Rules only, no LLM. Only fields the new mail does NOT give are taken (what it says always wins), and only from the
same sender address. Preferences come along too: excluded / required airlines, max transit, cheapest/fastest, the
offer file format, DG (a DG shipment stays DG). Nothing found → nothing changes (the usual ask / hand-over).
REPEAT_ORDER=off disables it.
"""
import os
import re

ON = os.environ.get("REPEAT_ORDER", "on").lower() != "off"

_LAST = r"(?:last|previous|prior|recent|earlier)"
_ORDER = r"(?:order|shipment|booking|request|inquiry|enquiry|rfq|quote|consignment|one|time)"
ASKS = re.compile("|".join([
    rf"\b(?:same|identical|similar)\s+(?:as|like|to)\s+(?:(?:my|our|the)\s+)?{_LAST}\s+{_ORDER}",
    rf"\b(?:just\s+)?(?:like|as)\s+(?:(?:my|our|the)\s+)?{_LAST}\s+{_ORDER}",
    rf"\b(?:repeat|re-?order|redo)\s+(?:of\s+)?(?:(?:my|our|the)\s+)?{_LAST}\s+{_ORDER}",
    r"\b(?:same|like|as)\s+(?:as\s+)?(?:before|last\s+time|usual)\b", r"\bthe\s+usual\s*(?:please|order|shipment|one)?\s*(?:[.!,]|$)",
    r"\bwie\s+(?:beim\s+)?(?:letzte[nms]?|vorige[nms]?)\s+mal\b",
    r"\bwie\s+(?:bei\s+)?(?:unsere[rnm]?|meine[rnm]?|die|der|das)\s+(?:letzte[nrms]?|vorige[nrms]?)\s+\w+",
    r"\bwie\s+(?:immer|gehabt|zuletzt)\b", r"\bgleiche\s+wie\s+(?:letzte|zuletzt)",
    r"\bcomme\s+(?:la\s+)?(?:derni[eè]re\s+fois|d'habitude|notre\s+derni[eè]re|ma\s+derni[eè]re)",
    r"\bcome\s+(?:l'ultima\s+volta|il\s+nostro\s+ultimo|al\s+solito|sempre)",
    r"\bcomo\s+(?:la\s+[uú]ltima\s+vez|(?:nuestro|mi)\s+[uú]ltimo|siempre|de\s+costumbre)",
    r"\bgeçen\s+(?:sefer|seferki|siparişimiz|siparişim)", r"\bzoals\s+(?:vorige\s+keer|de\s+vorige|gewoonlijk)",
]), re.I)

# fields of the previous rfq a repeat request inherits when the new one leaves them empty
# "Same as booking BK-12345, just three pallets": that exact booking, not the latest one (by_reference)
REFERENCE = re.compile(r"\b(?:same|identical|similar|like|as|repeat|re-?order|redo|wie|comme|come|como|zoals)\b[^.\n]{0,40}?"
                       r"\b(BK[\s_#:-]*[A-Z0-9]*\d[A-Z0-9]*|R-[A-Za-z0-9_-]{3,})\b", re.I)
PREFERENCES = ("excluded_airlines", "required_carriers", "max_transit_days", "offer_doc")


def asks(text: str) -> bool:
    return ON and bool(ASKS.search(text or "") or REFERENCE.search(text or ""))


def reference(text: str) -> str | None:
    """The booking reference or rate ID a repeat request names ("same as booking BK-12345")."""
    found = REFERENCE.search(text or "") if ON else None
    return found.group(1) if found else None


def _key(ref) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(ref or "").upper())


def by_reference(api, customer: str, session_id: int, ref: str) -> tuple[dict | None, str]:
    """(that booked session, "") or (None, why a person decides): exact hit only, this sender's only, booked only."""
    key = _key(ref)
    hits = [s for s in api.sessions() if s.get("id") != session_id and key in
            {_key((s.get("booking") or {}).get("booking_reference")), _key((s.get("booking") or {}).get("rate_id")),
             _key((s.get("quote") or {}).get("rate_id"))}]
    if not hits:
        return None, f"Repeat of {ref} asked, but no session has that reference"
    mine = [s for s in hits if _address(s.get("customer")) == _address(customer)]
    if not mine:
        return None, f"Repeat of {ref} asked, but that booking belongs to another customer"
    booked = [s for s in mine if (s.get("booking") or {}).get("booking_reference") and (s.get("rfq") or {}).get("origin")]
    if len(booked) != 1:
        return None, f"Repeat of {ref} asked, but it is {'ambiguous' if booked else 'not booked'}"
    return booked[0], ""


def _address(sender: str | None) -> str:
    """"Anna Meyer <anna@meyer.de>" and "ANNA@meyer.de" are the same customer."""
    found = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", sender or "")
    return found.group(0).lower() if found else (sender or "").strip().lower()


def previous(api, customer: str, session_id: int) -> dict | None:
    """The sender's latest earlier request that could be priced; a booked one first (that is "our last order")."""
    me = _address(customer)
    mine = [s for s in api.sessions() if s.get("id") != session_id and me and _address(s.get("customer")) == me
            and (s.get("rfq") or {}).get("origin") and (s.get("rfq") or {}).get("destination")]
    if not mine:
        return None
    booked = [s for s in mine if (s.get("booking") or {}).get("booking_reference")]
    return max(booked or mine, key=lambda s: s["id"])


def _has_weight(rfq: dict) -> bool:
    return any(p.get("weight_kg") for p in rfq.get("pieces") or [])


def fill(rfq: dict, missing: list[str], raw: dict | None, old: dict) -> tuple[list[str], list[str]]:
    """Fills `rfq` in place from `old`; returns (missing left, what was taken)."""
    taken = []
    for field in ("origin", "destination"):
        if not rfq.get(field) and old.get(field):
            rfq[field] = old[field]
            taken.append(f"{field} {old[field]}")
    if not rfq.get("pickup") and old.get("pickup") and taken and "origin" in taken[0]:
        rfq["pickup"] = old["pickup"]  # the old origin was a pickup zone's airport: the truck leg comes with it
    new = sum(p.get("count") or 0 for p in rfq.get("pieces") or [])
    was = sum(p.get("count") or 0 for p in old.get("pieces") or [])
    if not _has_weight(rfq) and _has_weight(old) and new > 1 and new != was:
        # "just three pallets this time": the new count wins, each piece as before (one old line only, else ask)
        if len(old["pieces"]) == 1:
            rfq["pieces"] = [{**old["pieces"][0], "count": new}]
            taken.append(f"pieces/weight ({new} pieces like before)")
            if not rfq.get("volume_m3") and old.get("volume_m3"):
                rfq["volume_m3"] = round(old["volume_m3"] * new / was, 3)
    elif not _has_weight(rfq) and _has_weight(old):  # shortcut: a count of 1 can't be told from "not said"
        rfq["pieces"] = [dict(p) for p in old["pieces"]]
        taken.append("pieces/weight")
        if not rfq.get("volume_m3") and old.get("volume_m3"):
            rfq["volume_m3"] = old["volume_m3"]
    if not rfq.get("commodity") and old.get("commodity"):
        rfq["commodity"] = old["commodity"]
        taken.append("commodity")
    if old.get("dangerous_goods") and not rfq.get("dangerous_goods") and any(t.startswith("pieces/weight") for t in taken):
        rfq["dangerous_goods"], rfq["dg_declared"] = True, old.get("dg_declared") or True  # same goods: still DG
        taken.append("dangerous goods")
    if (raw or {}).get("ask") is None and old.get("ask") and old["ask"] != rfq.get("ask"):
        rfq["ask"] = old["ask"]
        taken.append(f"ask {old['ask']}")
    for field in PREFERENCES:
        if not rfq.get(field) and old.get(field):
            rfq[field] = old[field]
            taken.append(field.replace("_", " "))
    filled = {"origin": bool(rfq.get("origin")), "destination": bool(rfq.get("destination")),
              "weight": _has_weight(rfq),
              "dimensions or volume": bool(rfq.get("volume_m3")) or any(p.get("length_cm") for p in rfq.get("pieces") or [])}
    return [m for m in missing if not filled.get(m)], taken
