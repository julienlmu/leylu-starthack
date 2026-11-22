"""POST /api/sessions/{id}/portal-rate: a rate a person got from the portal's web form, pasted as text.

The portal UI (start-hack.5u.ai/portal/ui) shows "Your rate" after a person solved its sum. The userscript
(agent/portal_helper.user.js) or a person posts that block's text here, with the airline it was asked for. The rate is
stored as a bid with `manual_portal: true`, the same shape as agent/portal_rate.py; the RFQ agent quotes with it.
Rules only: rate ID R-…, the total (a "total" line, else the largest amount), transit days, currency.
"""

import re

from pricing import chargeable_kg, weights

AIRLINES = {  # the portal's datalist (portal_ui.html)
    "AU": "Aurelia Air Cargo", "BX": "Borealis Freight Airways", "FQ": "Fjordline Air Cargo", "GN": "Gannet Airways",
    "IB": "Ibisair Cargo", "JP": "Juniper Cargo Lines", "LM": "Lumen Air Cargo", "MD": "Meridian Freightways",
    "NV": "Nova Atlas Cargo", "PL": "Polaris Air Logistics", "RV": "Riverbend Airlines Cargo", "SL": "Solace Air Cargo",
    "TM": "Tamarind Airways", "UV": "Ultraviolet Air Freight", "XC": "Xenon Cargo Airlines"}
_AMOUNT = r"\d{1,3}(?:[,.' ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
RATE_ID = re.compile(r"\bR-[A-Za-z0-9-]+")
TOTAL = re.compile(rf"\b(?:total|all[- ]in|price|rate|amount)\b[^\d\n]{{0,30}}?(?P<c1>EUR|USD|€|\$)?\s*(?P<n>{_AMOUNT})"
                   rf"\s*(?P<c2>EUR|USD|€|\$)?", re.I)
MONEY = re.compile(rf"(?P<c1>EUR|USD|€|\$)\s*(?P<n>{_AMOUNT})|(?P<n2>{_AMOUNT})\s*(?P<c2>EUR|USD|€)", re.I)
DAYS = re.compile(r"(\d+(?:[.,]\d)?)\s*(?:days?|d)\b|\btransit\D{0,20}(\d+(?:[.,]\d)?)", re.I)
CURRENCY = {"€": "EUR", "$": "USD"}


def number(raw: str) -> float:
    raw = raw.replace("'", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    if m := re.fullmatch(r"(\d{1,3}(?:[.,]\d{3})+)[.,](\d{1,2})", raw):
        return float(re.sub(r"[.,]", "", m.group(1)) + "." + m.group(2))
    return float(raw.replace(",", "."))


def _currency(*words) -> str | None:
    for word in words:
        if word:
            return CURRENCY.get(word, word.upper())
    return None


def parse(text: str, airline: str | None = None) -> dict | None:
    """The bid for this pasted result, or None when no amount can be read."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    rate_id = RATE_ID.search(text)
    plain = RATE_ID.sub(" ", text)  # "Rate ID R-GN7731A" is no amount
    total, currency = None, None
    totals = [m for m in TOTAL.finditer(plain) if not re.match(r"\s*(?:kg|cbm|m3|m³|%)", plain[m.end():], re.I)]
    money = [(number(m["n"] or m["n2"]), _currency(m["c1"], m["c2"])) for m in MONEY.finditer(plain)]
    if with_currency := [m for m in totals if m["c1"] or m["c2"]]:  # "Total EUR 1,284.50" first
        total, currency = number(with_currency[0]["n"]), _currency(with_currency[0]["c1"], with_currency[0]["c2"])
    elif money:  # else the largest amount with a currency ("€ 912,40")
        total, currency = max(money)
    elif totals:  # else "Total 1284.50" (no "Total weight 300 kg")
        total = number(totals[0]["n"])
    if not total or total <= 0:
        return None
    if not currency:
        currency = "USD" if re.search(r"\bUSD\b|\$", text) and not re.search(r"\bEUR\b|€", text) else "EUR"
    code = (airline or "").strip().upper()
    name = AIRLINES.get(code) or (airline or "").strip() or next(
        (n for n in AIRLINES.values() if n.lower() in text.lower()), None)
    if not name:
        return None
    days = DAYS.search(plain)
    return {"source": "carrier_bid", "leg": "air", "carrier": name, "airline_code": code if code in AIRLINES else None,
            "currency": currency, "total": round(total, 2),
            "transit_days": number(days.group(1) or days.group(2)) if days else None,
            "rate_id": rate_id.group(0) if rate_id else None, "manual_portal": True}


MAX_TEXT = 5000
PER_KG = (0.3, 50.0)  # EUR/USD per chargeable kg a portal rate can plausibly have; outside = a typo or a fake
MAX_TOTAL = 100_000.0
MAX_DAYS = 30.0
RATE_ID_OK = re.compile(r"R-[A-Za-z0-9-]{1,40}")


def checked(session: dict, airline: str, origin, destination, text: str) -> dict:
    """The bid for a paste on this session, or ValueError(why). The endpoint sits behind a public proxy with only a
    shared secret: everything that can reach a quote or a booking is checked here."""
    rfq = session.get("rfq") or {}
    if session.get("quote") or session.get("booking"):
        raise ValueError("this session is already quoted")
    if not rfq.get("origin") or not rfq.get("destination"):
        raise ValueError("this session has no lane yet")
    lane = (str(rfq["origin"]).upper(), str(rfq["destination"]).upper())
    if (str(origin or "").upper(), str(destination or "").upper()) != lane:
        raise ValueError(f"lane is not this session's {lane[0]}-{lane[1]}")
    code = airline.strip().upper()
    if code not in AIRLINES:
        raise ValueError("unknown airline code")
    if len(text) > MAX_TEXT:
        raise ValueError("pasted text too long")
    bid = parse(text, code)
    if bid is None:
        raise ValueError("no amount in the pasted portal result")
    if bid["currency"] not in ("EUR", "USD"):
        raise ValueError("currency must be EUR or USD")
    kg = chargeable_kg(*weights(rfq))
    if not 0 < bid["total"] <= MAX_TOTAL or (kg and not PER_KG[0] <= bid["total"] / kg <= PER_KG[1]):
        raise ValueError(f"total {bid['total']:,.2f} is implausible for {kg:g} chargeable kg")
    if bid["transit_days"] is not None and not 0 < bid["transit_days"] <= MAX_DAYS:
        raise ValueError("transit days out of range")
    if bid["rate_id"] and not RATE_ID_OK.fullmatch(bid["rate_id"]):
        raise ValueError("malformed rate ID")
    return bid
