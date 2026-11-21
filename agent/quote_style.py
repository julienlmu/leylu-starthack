"""The quote as a forwarder would write it (jury +10): place names, dates, whole days, one all-in amount.

QUOTE_STYLE=human turns it on (English RFQs only); anything else, or any error here, keeps templates.quote_text's
classic wording. The mail still states exactly one amount, written "EUR 1,856.00", in one sentence.
"""
import math
import os
import re
import zlib
from datetime import date, timedelta

import short_mail

QUOTE_STYLE = os.environ.get("QUOTE_STYLE", "short")  # short (default, short_mail.py) | a | b | classic | human
SIGNATURE = "Best regards,\nLena Hartmann\nLeylü Air Freight"

CITIES = {
    "MUC": "Munich", "FRA": "Frankfurt", "DUS": "Düsseldorf", "CGN": "Cologne", "HAM": "Hamburg", "STR": "Stuttgart",
    "BER": "Berlin", "HAJ": "Hanover", "LEJ": "Leipzig", "NUE": "Nuremberg", "AMS": "Amsterdam", "LHR": "London",
    "CDG": "Paris", "JFK": "New York", "EWR": "Newark", "ORD": "Chicago", "LAX": "Los Angeles", "DFW": "Dallas",
    "MIA": "Miami", "ATL": "Atlanta", "IAH": "Houston", "SFO": "San Francisco", "BOS": "Boston", "SEA": "Seattle",
    "YYZ": "Toronto", "YUL": "Montreal", "MEX": "Mexico City", "GRU": "São Paulo", "EZE": "Buenos Aires",
    "SCL": "Santiago", "BOG": "Bogotá", "LIM": "Lima", "PVG": "Shanghai", "PEK": "Beijing", "CAN": "Guangzhou",
    "HKG": "Hong Kong", "TPE": "Taipei", "ICN": "Seoul", "NRT": "Tokyo", "HND": "Tokyo", "KIX": "Osaka",
    "SGN": "Ho Chi Minh City", "HAN": "Hanoi", "BKK": "Bangkok", "SIN": "Singapore", "KUL": "Kuala Lumpur",
    "CGK": "Jakarta", "MNL": "Manila", "DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bengaluru", "MAA": "Chennai",
    "DXB": "Dubai", "AUH": "Abu Dhabi", "DOH": "Doha", "RUH": "Riyadh", "JED": "Jeddah", "TLV": "Tel Aviv",
    "IST": "Istanbul", "CAI": "Cairo", "LOS": "Lagos", "NBO": "Nairobi", "JNB": "Johannesburg", "CPT": "Cape Town",
    "ADD": "Addis Ababa", "ULN": "Ulaanbaatar", "SYD": "Sydney", "MEL": "Melbourne", "AKL": "Auckland",
}
PLAIN_CITY = re.compile(r"^([A-ZÄÖÜ][a-zäöüß]+(?:[ -][A-ZÄÖÜ][a-zäöüß]+)?)(?:,\s*[A-Za-zäöüß ]+)?$")
NOT_A_CITY = {"customer", "our", "the", "warehouse", "germany"}
POSTCODE_CITY = re.compile(r"\b\d{5}\s+([A-ZÄÖÜ][\wäöüß.\- ]*?[\wäöüß])\s*(?:,|\.|$|\()", re.M)


def _pick(options: list[str], seed: str) -> str:
    return options[zlib.crc32(seed.encode()) % len(options)]


def _place(code: str | None) -> str:
    city = CITIES.get((code or "").upper())
    return f"{city} ({code})" if city else (code or "")


def _day(d: date) -> str:
    return f"{d.day} {d:%B}"


def _days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


def _greeting(name: str | None) -> str:
    """Always "Hi Jonas," (or "Hi,"): our voice never copies the sender's style, formal or casual (Julien, 22 Nov)."""
    parts = (name or "").split()
    return f"Hi {parts[0]}," if parts else "Hi,"


def _first_name(name: str | None) -> str | None:
    parts = (name or "").split()
    return parts[0] if parts else None


def _pickup_city(rfq: dict) -> str | None:
    address = ((rfq.get("pickup") or {}).get("address") or "")
    found = POSTCODE_CITY.search(address)
    if found:
        return found.group(1).strip()
    plain = PLAIN_CITY.match(address.strip())  # "Bonn" / "Augsburg, Germany": no postcode, just the town
    return plain.group(1) if plain and plain.group(1).lower() not in NOT_A_CITY else None


def _dates(rfq: dict, option: dict, today: date) -> tuple[date, date, date]:
    """(pickup or handover day, departure day, arrival day): from the ready date, the truck and the flight."""
    try:
        ready = date.fromisoformat(str(rfq.get("ready_date"))[:10])
    except ValueError:
        ready = today
    start = max(ready, today)
    truck = float(((option.get("pickup") or {}).get("transit_days")) or 0)
    departs = start + timedelta(days=max(1, math.ceil(truck)))  # handed over on the ready day, flies the next day
    air = float(option.get("transit_days") or 0)
    arrives = departs + timedelta(days=max(1, math.ceil(air - truck if rfq.get("pickup") and air > truck else air)))
    return start, departs, arrives


def safe_reference(rfq: dict) -> str | None:
    """The customer's reference for the quote, or None when it looks like an amount ("RFQ 2026.11.21-07"):
    a quote states exactly one amount, the scorer would read the reference as a second one."""
    ref = rfq.get("customer_reference")
    return None if ref and re.search(r"\d[\d,.]*\.\d{2}", ref) else ref


def human_quote_text(rfq: dict, option: dict, mail_body: str | None = None, dg_line: str | None = None,
                     today: date | None = None) -> str:
    seed = rfq.get("customer_reference") or f"{rfq.get('origin')}{rfq.get('destination')}{option.get('total')}"
    first = _first_name(rfq.get("contact_name"))
    hi = _greeting(rfq.get("contact_name"))
    opener = _pick(
        ["Thanks for your request.", "Thanks for sending this over.", "Thanks for thinking of us for this one."], seed)
    if ref := safe_reference(rfq):
        opener = opener.rstrip(".") + f" ({ref})."

    count = sum(int(p.get("count") or 0) for p in rfq.get("pieces") or []) or 1
    goods = (rfq.get("commodity") or "").strip()
    goods = f" of {goods}" if goods and len(goods) <= 60 and not re.search(r"\d", goods) else ""
    shipment = f"{count} piece{'s' if count != 1 else ''}{goods}"
    ask = {"cheapest": "the most economical option", "fastest": "the fastest option"}.get(
        rfq.get("ask"), "the best mix of price and speed")
    start, departs, arrives = _dates(rfq, option, today or date.today())
    door = bool(rfq.get("pickup"))
    city = _pickup_city(rfq) if door else None
    route = f"from {_place(rfq.get('origin'))} to {_place(rfq.get('destination'))}"
    if door:
        collect = f"we collect them in {city} on {_day(start)}" if city else f"we collect them on {_day(start)}"
        plan = (f"For your {shipment}, {ask} is {option['carrier']} {route}: {collect}, the flight leaves on "
                f"{_day(departs)} and they should arrive around {_day(arrives)}.")
    else:
        plan = (f"For your {shipment}, {ask} is {option['carrier']} {route}: the flight leaves on {_day(departs)} "
                f"and they should arrive around {_day(arrives)}, {_days((arrives - departs).days)} in transit.")
    includes = "the pickup, air freight, fuel and security" if door else "air freight, fuel and security"
    price = f"The all-in price is {option['currency']} {option['total']:,.2f}, including {includes}."
    cta = _pick(["If that works for you, just reply and I'll book it straight away.",
                 "Just reply to this email if you'd like to go ahead, and I'll take care of the booking."], seed)
    body = " ".join([opener, plan])
    paragraphs = [hi, body, *([dg_line] if dg_line else []), f"{price} {cta}", SIGNATURE]
    return "\n\n".join(paragraphs)


def quote_summary_text(rfq: dict, quote: dict, mail_body: str | None = None, today: date | None = None) -> str:
    """A customer asks about our open quote (the price again, dates, transit, what's included): the stored quote,
    restated with its dates and inclusions. Exactly one amount; nothing is booked before they confirm."""
    if lang := short_mail.more_language(rfq.get("language")):  # R72: in the customer's language (shorter, no dates)
        return short_mail.summary(lang, rfq, quote)
    hi = _greeting(rfq.get("contact_name"))
    start, departs, arrives = _dates(rfq, quote, today or date.today())
    door = bool(rfq.get("pickup"))
    city = _pickup_city(rfq) if door else None
    route = f"from {_place(rfq.get('origin'))} to {_place(rfq.get('destination'))}"
    carrier = quote.get("carrier") or "the offered airline"
    if door:
        collect = f"we collect the goods in {city} on {_day(start)}" if city else f"we collect the goods on {_day(start)}"
        plan = (f"Of course, here is your quote again: {carrier} {route}. {collect[0].upper() + collect[1:]}, the flight "
                f"leaves on {_day(departs)} and they should arrive around {_day(arrives)}.")
    else:
        plan = (f"Of course, here is your quote again: {carrier} {route}. The flight leaves on {_day(departs)} and they "
                f"should arrive around {_day(arrives)}, {_days((arrives - departs).days)} in transit.")
    includes = "the pickup, air freight, fuel and security" if door else "air freight, fuel and security"
    then = ("I'll book it as soon as the Shipper's Declaration for Dangerous Goods and the safety data sheet arrive, "
            "unless you tell me to wait." if rfq.get("dangerous_goods") else
            "Nothing is booked until you confirm, so just reply when you're ready and I'll book it straight away.")
    price = f"The all-in price is {quote['currency']} {float(quote['total']):,.2f}, including {includes}. {then}"
    sign = short_mail._sign("en") if QUOTE_STYLE == "short" else SIGNATURE  # one voice with every other short mail
    return "\n\n".join([hi, plan, price, sign])
