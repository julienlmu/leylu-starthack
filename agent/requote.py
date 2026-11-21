"""REQUOTE (rfq_agent.requote_after_change, R86/R87): which customer replies after our quote change the shipment.

Rules only, no LLM. kind(text, rfq):
- "requote": a change word ("changed", "updated", "instead", "now is", "geändert" …) or our own question just before
  it, plus a weight in the mail (kg/lbs); the figures must differ from what we quoted ("is the 1,317 kg we quoted
  incl. pallets?" or "thanks for the update" with our own numbers is no change).
- "ask": a change of pieces / volume / dimensions without a weight ("now 5 pieces, 8.18 cbm"): one short question for
  the figures, never a guessed weight; their answer is re-quoted (rfq.requote_asked).
- None: anything else; "can you also quote 2 pallets to ORD" / "another shipment" is a new request, never a change of
  this one (a person, as before).
grounded(): the new reading has every number the customer wrote (total or per piece), else we ask instead of quoting
a misread. A second unclear change goes to a person (MAX_ASKS).
"""

import re

MAX_ASKS = 1
REQUOTE_ASK = re.compile(r"\b(?:chang\w*|updat\w*|correct\w*|amend\w*|revis\w*|instead|now (?:is|are|it'?s)|(?:is|are) now|"
                         r"final packing list|ge(?:ä|ae)ndert|aktualisier\w*|korrigier\w*|neue[ns]? angebot)\b", re.I)
# The new weight must be in the mail (R86/R87: "5 pieces, 1317 kg gross weight, 8.18 cbm")
NEW_FIGURES = re.compile(r"\b\d[\d.,']*\s*(?:kg|kgs|kilos?|kilograms?|lbs?)\b", re.I)
THANKS_UPDATE = re.compile(r"\bthanks?(?: you)? for (?:the|your) update\b", re.I)
ALSO = re.compile(r"\b(?:as\s+well|also\s+(?:quote|price|need|send|have|get|ship)|in\s+addition|additionally|"
                  r"separate(?:ly)?|another|a\s+second\s+(?:shipment|quote|request)|one\s+more\s+(?:shipment|quote)|"
                  r"zusätzlich|ebenfalls|noch\s+eine\s+(?:sendung|anfrage)|weitere\s+(?:sendung|anfrage))\b", re.I)
INSTEAD = re.compile(r"\b(?:instead|statt\w*|rather\s+than|replac\w*)\b", re.I)
_NUM = r"(\d{1,3}(?:[.,' ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
KG = re.compile(_NUM + r"\s*(?:kg|kgs|kilos?|kilograms?)\b", re.I)
LBS = re.compile(_NUM + r"\s*(?:lbs?|pounds)\b", re.I)
M3 = re.compile(_NUM + r"\s*(?:cbm|m3|m³|cubic\s+met(?:er|re)s?|kubikmeter)\b", re.I)
PIECES = re.compile(r"\b(\d{1,4})\s*(?:pcs|pieces?|pallets?|plts?|cartons?|ctns?|crates?|boxes|cases?|colli|kolli|"
                    r"packages?|pkgs?|stück|stk|paletten?|packstücke)\b", re.I)
DIMS = re.compile(r"\b\d{2,4}(?:[.,]\d+)?\s*[x×*]\s*\d{2,4}(?:[.,]\d+)?\s*[x×*]\s*\d{2,4}(?:[.,]\d+)?\b", re.I)
CODE = re.compile(r"\b[A-Z]{3}\b")

ASK = {
    "en": "Thanks for the update. So that I quote exactly the new shipment: could you send me the total number of "
          "pieces, the total gross weight in kg and the volume in cbm (or the dimensions of each piece)? I'll send "
          "the new all-in price right away.",
    "de": "Danke für die Änderung. Damit ich genau die neue Sendung anbiete: Können Sie mir bitte die Anzahl der "
          "Packstücke, das Gesamtgewicht in kg und das Volumen in cbm (oder die Maße je Packstück) schicken? Den neuen "
          "Gesamtpreis bekommen Sie dann sofort.",
}


def number(raw: str) -> float:
    """"1,317" / "1.317" / "1 317" → 1317; "8,18" / "8.18" → 8.18; "1,317.50" → 1317.5."""
    raw = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:[.,' ]\d{3})+", raw):
        return float(re.sub(r"[.,' ]", "", raw))
    if m := re.fullmatch(r"(\d{1,3}(?:[.,' ]\d{3})+)[.,](\d+)", raw):
        return float(re.sub(r"[.,' ]", "", m.group(1)) + "." + m.group(2))
    return float(raw.replace(",", "."))


def stated(text: str) -> dict:
    """The cargo figures a mail writes: kg (lbs converted), m3, piece counts, whether it gives dimensions."""
    return {"kg": [number(m) for m in KG.findall(text)] + [round(number(m) * 0.45359237, 1) for m in LBS.findall(text)],
            "m3": [number(m) for m in M3.findall(text)], "pieces": [int(m) for m in PIECES.findall(text)],
            "dims": bool(DIMS.search(text))}


def known(rfq: dict) -> dict:
    """The figures of a reading: total and per-piece kg, the volume, total and per-line counts."""
    pieces = rfq.get("pieces") or []
    kg = sum(int(p.get("count") or 1) * float(p.get("weight_kg") or 0) for p in pieces)
    m3 = rfq.get("volume_m3")
    if m3 is None and pieces and all(p.get("length_cm") and p.get("width_cm") and p.get("height_cm") for p in pieces):
        m3 = sum(int(p.get("count") or 1) * p["length_cm"] * p["width_cm"] * p["height_cm"] for p in pieces) / 1e6
    return {"kg": [x for x in [kg, *(p.get("weight_kg") for p in pieces)] if x],
            "m3": [x for x in [m3] if x],
            "pieces": [x for x in [sum(int(p.get("count") or 1) for p in pieces), *(p.get("count") for p in pieces)] if x]}


def _close(value: float, values: list, tolerance: float) -> bool:
    return any(abs(value - v) <= tolerance * max(abs(v), 1.0) for v in values)


def _differs(said: dict, old: dict) -> bool:
    return (any(not _close(v, old["kg"], 0.01) for v in said["kg"]) or any(not _close(v, old["m3"], 0.02)
                                                                           for v in said["m3"])
            or any(v not in old["pieces"] for v in said["pieces"]))


def kind(text: str, rfq: dict) -> str | None:
    """"requote", "ask" or None for a reply to our open quote."""
    text = THANKS_UPDATE.sub(" ", text or "")
    if ALSO.search(text) and not INSTEAD.search(text):
        return None  # another shipment, not a change of this one
    asked = bool(rfq.get("requote_asked"))
    if not (asked or REQUOTE_ASK.search(text)):
        return None
    said = stated(text)
    if said["kg"]:
        return "requote" if asked or _differs(said, known(rfq)) or said["dims"] else None
    if said["pieces"] or said["m3"] or said["dims"]:
        return "ask" if asked or said["dims"] or _differs(said, known(rfq)) else None
    return None


def grounded(said: dict, new: dict) -> bool:
    """Every figure the customer wrote is in the new reading (as a total or per piece)."""
    have = known(new)
    return (all(_close(v, have["kg"], 0.01) for v in said["kg"]) and all(_close(v, have["m3"], 0.03) for v in said["m3"])
            and all(v in have["pieces"] for v in said["pieces"]))


def ask_text(rfq: dict) -> str:
    lang = (rfq.get("language") or "en")[:2].lower()
    lang = lang if lang in ASK else "en"
    first = (rfq.get("contact_name") or "").split()[:1]
    hi = ("Hallo" if lang == "de" else "Hi") + (f" {first[0]}," if first else ",")
    import short_mail
    return f"{hi}\n\n{ASK[lang]}\n\n{short_mail._sign(lang)}"
