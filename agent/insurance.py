"""INSURANCE (default on; off = freight only, as before): cargo insurance the customer wants inside the all-in price.

R91 / session 93 (too_low): "please include cargo insurance in the all-in: goods value 22000 EUR, insured at 110 % of
that value, premium rate 0.40 %". We quoted the freight only (927.95); 5U expected 927.95 + 22000 × 1.10 × 0.004 = 96.80.

Rules on the mail text, no LLM:
- terms(text): asked? goods value (+ currency), cover (110 % of the value / CIF / invoice value; default 100 %), premium
  rate (% or ‰), minimum premium. "No insurance needed", "we insure it ourselves", "quote insurance separately" are no ask.
- premium(terms, fx): max(minimum, value × cover × rate) in EUR. A value in another currency uses the price result's
  exchange rate; none → None.
- add(result, rfq): every priced option gets the premium in its total and a "Cargo insurance" breakdown line, plus
  option["insurance"] = {"total": premium, ...} (the backend's booking check adds it back to a fresh air rate).
Incomplete terms (no value or no rate): the quote gate asks for them (gate.review), never a freight-only all-in.
"""

import os
import re
from decimal import ROUND_HALF_UP, Decimal

ON = os.environ.get("INSURANCE", "on").lower() != "off"

WORD = r"\w*(?:insur|versicher|assuran|seguro|assicura)\w*"
ASKED = re.compile(rf"\b{WORD}", re.I)
# the customer wants it in the price: "include cargo insurance", "insured at 110 %", "all-in incl. insurance", a premium
INCLUDE = re.compile(r"\b(?:includ\w*|incl\.?|inkl\.?|inklusive|einschlie\w*|all[- ]in|add\w*|plus|with|mit|insured\s+"
                     r"(?:at|for)|premium|prämie|praemie|cover\s+(?:it|the|this)|versichert|inclu\w*|compris\w*)\b", re.I)
NOT_ASKED = re.compile(
    rf"\b(?:no|without|kein\w*|ohne|sans|sin|senza)\s+(?:\w+\s+){{0,2}}?{WORD}"
    rf"|\b{WORD}\s+(?:is\s+|are\s+)?(?:not\s+(?:needed|required|necessary|wanted)|unnecessary|not\s+part)"
    rf"|\b{WORD}\s+(?:\w+\s+){{0,3}}?(?:separately|on\s+top|as\s+an?\s+option|optional\w*|extra)\b"
    rf"|\b(?:separate|optional)\s+(?:\w+\s+)?{WORD}"
    rf"|\b(?:own|our|existing)\s+(?:\w+\s+)?{WORD}|\bwe\s+(?:insure|cover)\s+(?:it|this|them|the\s+\w+)\s+ourselves\b"
    rf"|\b(?:nicht|keine?)\s+(?:\w+\s+){{0,2}}?{WORD}|\b{WORD}\w*\s+(?:nicht|ist\s+nicht)\b", re.I)
_NUM = r"\d[\d.,' ]*\d|\d"
_CUR = r"(?:EUR|€|euros?|USD|US\$|\$|GBP|£|CHF)"
VALUE = re.compile(
    rf"\b(?:goods|cargo|commercial|invoice|declared|shipment|insured|insurance|CIF|merchandise|consignment|"
    rf"customs|waren|rechnungs)\s*-?\s*(?:value|wert)\b(?:\s+(?:of|is|amounts?\s+to|=|:|is\s+about|approx\.?|"
    rf"around|ca\.?)){{0,2}}\s*:?\s*(?P<c1>{_CUR})?\s*(?P<n>{_NUM})\s*(?P<k>k\b|tsd\.?|thousand)?\s*(?P<c2>{_CUR})?"
    rf"|\bvalue\s+of\s+(?:the\s+)?(?:goods|cargo|shipment)\s*(?:is|of|:|=)?\s*(?P<c3>{_CUR})?\s*(?P<n2>{_NUM})\s*"
    rf"(?P<k2>k\b)?\s*(?P<c4>{_CUR})?"
    rf"|\b(?:valued\s+at|(?:is|are)\s+worth|worth\s+of|worth)\s*(?:about\s+|around\s+|approx\.?\s+|ca\.?\s+)?"
    rf"(?P<c5>{_CUR})?\s*(?P<n3>{_NUM})\s*(?P<k3>k\b)?\s*(?P<c6>{_CUR})?", re.I)
PERCENT = re.compile(rf"(?P<n>{_NUM})\s*(?P<u>%|‰|per\s*cent|percent|prozent|promille|per\s+mille)", re.I)
RATE_WORDS = re.compile(r"\b(?:premium|rate|prämie|praemie|tarif|taux|tasa|tasso)\b", re.I)
COVER_WORDS = re.compile(r"\b(?:of\s+(?:the\s+|that\s+|its\s+|this\s+)?(?:CIF|invoice|goods|commercial|cargo|declared)?\s*"
                         r"(?:value|wert)|insured\s+(?:at|for)|cover\w*|deckung|versichert\s+(?:mit|zu)|des\s+warenwert\w*)",
                         re.I)
MINIMUM = re.compile(rf"\bmin(?:imum|\.)?\s+(?:premium|charge|prämie)?\s*(?:of|is|:|=)?\s*(?P<c1>{_CUR})?\s*(?P<n>{_NUM})"
                     rf"\s*(?P<c2>{_CUR})?", re.I)
CODES = {"€": "EUR", "euro": "EUR", "euros": "EUR", "$": "USD", "us$": "USD", "£": "GBP"}


def number(raw: str) -> float:
    """"22000" / "22,000" / "22.000" / "22 000" → 22000; "0.40" / "0,4" → 0.4; "1.234,50" → 1234.5."""
    raw = raw.strip().replace("'", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    if m := re.fullmatch(r"(\d{1,3}(?:[.,]\d{3})+)[.,](\d{1,2})", raw):
        return float(re.sub(r"[.,]", "", m.group(1)) + "." + m.group(2))
    return float(raw.replace(",", "."))


def _code(*words) -> str | None:
    for word in words:
        if word:
            return CODES.get(word.lower(), word.upper())
    return None


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?;])\s+(?=\S)|\n+", text) if s.strip()]


def terms(text: str) -> dict | None:
    """The customer's insurance ask, or None when the mail doesn't ask to include insurance."""
    if not ON or not ASKED.search(text or ""):
        return None
    sentences = _sentences(text)
    about = [s for s in sentences if ASKED.search(s) and not NOT_ASKED.search(s)]
    if not about or not any(INCLUDE.search(s) for s in about):
        return None  # "no insurance needed", "we insure it ourselves", "quote insurance separately"
    near = " ".join(s for s in sentences if ASKED.search(s) or VALUE.search(s) or PERCENT.search(s))
    out = {"asked": True, "value": None, "currency": None, "cover": 1.0, "rate": None, "minimum": None}
    if m := VALUE.search(near):
        raw = m["n"] or m["n2"] or m["n3"]
        value = number(raw) * (1000 if (m["k"] or m["k2"] or m["k3"]) else 1)
        out["value"], out["currency"] = value, _code(m["c1"], m["c2"], m["c3"], m["c4"], m["c5"], m["c6"]) or "EUR"
    for p in PERCENT.finditer(near):
        value = round(number(p["n"]) / (1000 if p["u"].lower() in ("‰", "promille", "per mille") else 100), 10)
        before, after = near[max(0, p.start() - 40):p.start()], near[p.end():p.end() + 40]
        if COVER_WORDS.search(after[:25]) or re.search(r"insured\s+(?:at|for)\s*$|deckung\s*$", before, re.I) \
                or (value >= 0.5 and not RATE_WORDS.search(before[-25:])):
            out["cover"] = value  # 110 % of the value (a premium is never half the value)
        elif out["rate"] is None:
            out["rate"] = value
    if m := MINIMUM.search(near):
        out["minimum"] = number(m["n"])
    out["complete"] = bool(out["value"] and out["rate"])
    return out


def premium(t: dict, fx: dict | None = None) -> float | None:
    """The premium in EUR, or None (terms incomplete, or a value in a currency we have no rate for)."""
    if not t or not t.get("complete"):
        return None
    d = lambda x: Decimal(str(x))  # noqa: E731  the backend's money(): Decimal, half up (71.225 → 71.23)
    amount = max(d(t["value"]) * d(t.get("cover") or 1.0) * d(t["rate"]), d(t.get("minimum") or 0))
    if (t.get("currency") or "EUR") != "EUR":
        rate = (fx or {}).get(t["currency"])  # EUR per unit, as the price result gives it
        if not rate:
            return None
        amount *= d(rate)
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def label(t: dict) -> str:
    cover = f"{t.get('cover', 1.0) * 100:g} % of " if t.get("cover", 1.0) != 1.0 else ""
    return (f"Cargo insurance ({cover}{t.get('currency') or 'EUR'} {t['value']:,.2f} at {t['rate'] * 100:g} %"
            + (f", minimum {t['minimum']:,.2f}" if t.get("minimum") else "") + ")")


def add(result: dict, rfq: dict) -> dict:
    """The price result with the premium in every option's all-in (in place too). Nothing to add → unchanged."""
    t = (rfq or {}).get("insurance")
    if not ON or not isinstance(t, dict) or not t.get("complete") or not isinstance(result, dict):
        return result
    amount = premium(t, result.get("fx"))
    if amount is None:
        result["insurance_missing"] = "no exchange rate for the goods value"
        return result
    seen = set()
    for option in [*(result.get("options") or []), result.get("chosen")]:
        if not isinstance(option, dict) or id(option) in seen or option.get("total") is None or option.get("insurance") \
                or option.get("insurance_eur"):  # the deploy thread's own patch (d3bd7d2) added it already
            continue
        seen.add(id(option))
        option["total"] = float(Decimal(str(option["total"])) + Decimal(str(amount)))
        if option.get("total_eur") is not None:
            option["total_eur"] = float(Decimal(str(option["total_eur"])) + Decimal(str(amount)))
        option["breakdown"] = [*(option.get("breakdown") or []), {"label": label(t), "amount": amount}]
        option["insurance"] = {"total": amount, "value": t["value"], "currency": t.get("currency") or "EUR",
                               "cover": t.get("cover", 1.0), "rate": t["rate"], "minimum": t.get("minimum")}
    why = result.get("why") or ""
    result["why"] = f"{why} Cargo insurance EUR {amount:,.2f} added to each all-in.".strip()
    return result
