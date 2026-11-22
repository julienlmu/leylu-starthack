"""Cargo insurance asked "in the all-in price" (R91 too_low: 10 of 11 teams left it out): the premium the mail's own
terms give is added to every priced option, so the quote's one amount includes it. Rules only, no LLM.

"goods value 22000 EUR, insured at 110 % of that value, premium rate 0.40 %" → 22000 × 1.10 × 0.40 % = EUR 96.80.
Insured share: the % written next to "insured"/"of the value" (CIF + 10 % → 110 %), else 100 %. A minimum premium
written in the mail wins when it is higher. Nothing is added without a written premium rate and goods value, when the
mail says no insurance is wanted, or when the value's currency is not the option's. INSURANCE=off disables it.
"""
import os
import re

ON = os.environ.get("INSURANCE", "on").lower() != "off"
ASKED = re.compile(r"\b(?:insur\w*|versicher\w*|assuran\w*|seguro|assicura\w*|verzeker\w*|sigorta\w*)", re.I)
NOT_WANTED = re.compile(r"\b(?:no|without|not|exclud\w*|ohne|keine?|sans|sin|senza)\s+(?:\w+\s+){0,2}?"
                        r"(?:insur\w*|versicher\w*|assuran\w*|seguro|assicura\w*)|"
                        r"\b(?:insur\w*|versicher\w*)\s+(?:is\s+)?(?:not\s+(?:needed|required|necessary)|"
                        r"nicht\s+(?:nötig|erforderlich|notwendig))|we\s+(?:insure|cover)\s+(?:it|the\s+goods)\s+ourselves", re.I)
NUM = r"(\d{1,3}(?:[.,' ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?)"
CUR = r"(EUR|€|USD|\$|GBP|£|CHF)"
VALUE = re.compile(rf"\b(?:goods|cargo|invoice|commercial|shipment|declared|insured)?\s*value\b[^.\n\d€$£]{{0,40}}?"
                   rf"(?:{CUR}\s*{NUM}|{NUM}\s*{CUR})|\b(?:warenwert|rechnungswert|valeur|valor|valore)\b[^.\n\d€$£]{{0,30}}?"
                   rf"(?:{CUR}\s*{NUM}|{NUM}\s*{CUR})", re.I)
COVER = re.compile(r"\b(?:insured|covered|cover|versichert|assur[ée]e?s?)\b[^.\n%]{0,25}?(\d{2,3}(?:[.,]\d+)?)\s*%|"
                   r"(\d{2,3}(?:[.,]\d+)?)\s*%\s*(?:of\s+(?:the|that|its)?\s*(?:goods\s+|invoice\s+)?value|des\s+warenwerts)|"
                   r"\bCIF\s*\+\s*(\d{1,2})\s*%", re.I)
RATE = re.compile(r"\b(?:premium|prämie|praemie|prime|prima|premio)\b[^.\n%‰]{0,25}?(\d+(?:[.,]\d+)?)\s*(%|‰|per\s*mille|promille)|"
                  r"(\d+(?:[.,]\d+)?)\s*(%|‰)\s*(?:premium|prämie|insurance\s+premium|rate)", re.I)
MINIMUM = re.compile(rf"\b(?:min(?:imum)?\.?|mindest\w*)\s+(?:premium|prämie)?[^.\n\d€$£]{{0,15}}?(?:{CUR}\s*{NUM}|{NUM}\s*{CUR})", re.I)
CODES = {"€": "EUR", "$": "USD", "£": "GBP"}


def _number(text: str) -> float:
    text = text.replace("'", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):  # 22,000 / 22.000: thousands
        return float(re.sub(r"[.,]", "", text))
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+[.,]\d{1,2}", text):  # 22.000,50 / 22,000.50
        return float(re.sub(r"[.,]", "", text[:-3]) + "." + text[-2:])
    return float(text.replace(",", "."))


def _money(m) -> tuple[float, str] | None:
    groups = [g for g in m.groups() if g]
    cur = next((g for g in groups if re.fullmatch(CUR, g, re.I)), None)
    num = next((g for g in groups if not re.fullmatch(CUR, g, re.I)), None)
    if not (cur and num):
        return None
    return _number(num), CODES.get(cur, cur.upper())


def terms(text: str) -> dict | None:
    """{"premium", "currency", "why"} when the mail asks for insurance with enough terms to price it, else None."""
    if not (ON and text and ASKED.search(text)) or NOT_WANTED.search(text):
        return None
    value = next((v for m in VALUE.finditer(text) if (v := _money(m))), None)
    rate = RATE.search(text)
    if not (value and rate):
        return None
    rate_value = _number(rate.group(1) or rate.group(3))
    unit = (rate.group(2) or rate.group(4) or "%").lower()
    rate_share = rate_value / (1000 if unit in ("‰", "per mille", "promille") or "mille" in unit else 100)
    cover = COVER.search(text)
    share = 1.0
    if cover:
        if cover.group(3):
            share = 1 + _number(cover.group(3)) / 100
        else:
            share = _number(cover.group(1) or cover.group(2)) / 100
    if not 0.5 <= share <= 2 or not 0 < rate_share < 0.2:
        return None  # a misread, never priced
    amount, currency = value
    premium = round(amount * share * rate_share, 2)
    if (low := MINIMUM.search(text)) and (floor := _money(low)) and floor[1] == currency:
        premium = max(premium, floor[0])
    why = f"insurance {currency} {amount:,.0f} × {share * 100:g} % × {rate_share * 100:g} % = {currency} {premium:,.2f}"
    return {"premium": premium, "currency": currency, "why": why}


def apply(result: dict, found: dict | None) -> dict:
    """Adds the premium to every option in the option's currency (only the same currency as the goods value)."""
    if not found or not result:
        return result
    for option in [*(result.get("options") or []), *([result["chosen"]] if result.get("chosen") else [])]:
        if option.get("insurance_added") or (option.get("currency") or "EUR") != found["currency"]:
            continue
        option["total"] = round(float(option["total"]) + found["premium"], 2)
        if option.get("total_eur") is not None and found["currency"] == "EUR":
            option["total_eur"] = round(float(option["total_eur"]) + found["premium"], 2)
        option["breakdown"] = [*(option.get("breakdown") or []), {"label": f"Cargo insurance ({found['why']})",
                                                                   "amount": found["premium"]}]
        option["insurance_added"] = True
        option["insurance_premium"] = found["premium"]  # backend/booking.py: an unchanged air rate is no price change
    return result


def price(api, rfq: dict, bids, **kwargs) -> dict:
    """api.price with the insurance premium the RFQ's own terms give (rfq["insurance"]) added to every option."""
    return apply(api.price(rfq, bids, **kwargs), (rfq or {}).get("insurance"))
