"""Airports we can price, and the codes customers (or the LLM) use for the same city.

5U's lanes fly from six German airports to ~40 destinations (start-kit carrier list, rate sheets, portal ports). A mail
that says "Tokyo", "New York" or "Shanghai" can come back from the extraction as HND, EWR, NYC or SHA: no lane, no
price, and the round goes to a person. Free, in code:
- a city name instead of a code ("Tokyo") becomes its airport right after the extraction (a name never prices);
- a code is kept as extracted and priced first (the portal's lanes change during the day). Only when it gets no price,
  the RFQ agent prices the same city's airport that our lanes fly (`aliased`).
AIRPORT_ALIASES=off switches both off.
"""

import csv
import json
import os
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "backend" / "data"
ENABLED = os.environ.get("AIRPORT_ALIASES", "on").lower() != "off"

# Other airports and metropolitan (city) codes of a city we serve → the airport our lanes use.
SAME_CITY = {
    "NYC": "JFK", "EWR": "JFK", "LGA": "JFK",          # New York
    "TYO": "NRT", "HND": "NRT",                        # Tokyo
    "SHA": "PVG",                                      # Shanghai Hongqiao
    "BJS": "PEK", "PKX": "PEK",                        # Beijing Daxing
    "SAO": "GRU", "VCP": "GRU", "CGH": "GRU",          # São Paulo
    "BUE": "EZE", "AEP": "EZE",                        # Buenos Aires
    "SEL": "ICN", "GMP": "ICN",                        # Seoul
    "DMK": "BKK",                                      # Bangkok Don Mueang
    "DWC": "DXB",                                      # Dubai World Central
    "CHI": "ORD", "MDW": "ORD",                        # Chicago
    "DAL": "DFW", "QDF": "DFW",                        # Dallas
    "YTO": "YYZ", "YTZ": "YYZ",                        # Toronto
    "TSA": "TPE",                                      # Taipei Songshan
    "NLU": "MEX",                                      # Mexico City Felipe Ángeles
    "UBN": "ULN",                                      # Ulaanbaatar (new airport's code)
    "AVV": "MEL",                                      # Melbourne Avalon
    "WSI": "SYD",                                      # Western Sydney
    "SZB": "KUL",                                      # Kuala Lumpur Subang
    "NMI": "BOM",                                      # Navi Mumbai
    "DXN": "DEL",                                      # Delhi Noida
    "DIA": "DOH",                                      # Doha (old airport)
    "SPX": "CAI",                                      # Cairo Sphinx
    "HLA": "JNB",                                      # Johannesburg Lanseria
    "WIL": "NBO",                                      # Nairobi Wilson
    "XSP": "SIN",                                      # Singapore Seletar
}

# City names the extraction sometimes returns instead of a code.
CITY = {
    "new york": "JFK", "tokyo": "NRT", "shanghai": "PVG", "beijing": "PEK", "peking": "PEK", "sao paulo": "GRU",
    "são paulo": "GRU", "buenos aires": "EZE", "seoul": "ICN", "bangkok": "BKK", "dubai": "DXB", "chicago": "ORD",
    "dallas": "DFW", "toronto": "YYZ", "taipei": "TPE", "mexico city": "MEX", "ulaanbaatar": "ULN",
    "melbourne": "MEL", "sydney": "SYD", "kuala lumpur": "KUL", "mumbai": "BOM", "bombay": "BOM", "delhi": "DEL",
    "new delhi": "DEL", "doha": "DOH", "cairo": "CAI", "johannesburg": "JNB", "nairobi": "NBO", "singapore": "SIN",
    "hong kong": "HKG", "lagos": "LOS", "riyadh": "RUH", "tel aviv": "TLV", "los angeles": "LAX", "miami": "MIA",
    "atlanta": "ATL", "lima": "LIM", "bogota": "BOG", "bogotá": "BOG", "santiago": "SCL", "asuncion": "ASU",
    "asunción": "ASU", "kathmandu": "KTM", "papeete": "PPT", "antananarivo": "TNR", "manila": "MNL",
    "ho chi minh city": "SGN", "saigon": "SGN",
    "munich": "MUC", "münchen": "MUC", "muenchen": "MUC", "frankfurt": "FRA", "dusseldorf": "DUS",
    "düsseldorf": "DUS", "duesseldorf": "DUS", "cologne": "CGN", "köln": "CGN", "koeln": "CGN",
    "hamburg": "HAM", "stuttgart": "STR",
}

_known: set[str] = set()


def known() -> set[str]:
    """Every airport code that appears in a lane: carrier list, rate sheets, portal ports, pickup zones."""
    if _known:
        return _known
    codes: set[str] = set()
    try:
        with (DATA / "start-kit" / "carrier-list.csv").open(newline="") as f:
            codes |= {c for row in csv.DictReader(f) if row["kind"].strip() == "airline" for c in row["serves"].split()}
    except (OSError, KeyError):
        pass
    try:
        tariffs = json.loads((DATA / "tariffs.json").read_text())
        for sheet in tariffs["sheets"] if isinstance(tariffs, dict) else tariffs:
            for lane in sheet["lanes"]:
                codes |= set(lane["lane"].split("-"))
    except (OSError, KeyError, TypeError, ValueError):
        pass
    try:
        for lane in json.loads((DATA / "portal_ports.json").read_text())["lanes"]:
            codes |= {lane["origin"], lane["destination"]}
    except (OSError, KeyError, TypeError, ValueError):
        pass
    try:
        with (DATA / "pickup_zones.csv").open(newline="") as f:
            codes |= {row["airport"] for row in csv.DictReader(f)}
    except (OSError, KeyError):
        pass
    _known.update(c for c in codes if c and c.isalpha() and len(c) == 3)
    return _known


def city_code(value: str | None) -> tuple[str | None, str | None]:
    """A city name the extraction returned instead of a code → (its airport, note). Codes are never changed here."""
    if not ENABLED or not value or (len(value.strip()) == 3 and value.strip().isalpha()):
        return value, None
    target = CITY.get(value.strip().lower())
    if target and target in known():
        return target, f"{value} → {target}"
    return value, None


def aliased(rfq: dict) -> tuple[dict, str] | None:
    """The same request at the same city's airport that our lanes fly (HND → NRT, EWR → JFK), with a note; None if
    neither airport has such an alias. Only used after the extracted codes got no price."""
    if not ENABLED:
        return None
    lanes, changed, notes = known(), dict(rfq), []
    for field in ("origin", "destination"):
        code = (rfq.get(field) or "").strip().upper()
        target = SAME_CITY.get(code)
        if target and target in lanes and code not in lanes:
            changed[field] = target
            notes.append(f"{field} {code} → {target}")
    return (changed, f"{'; '.join(notes)} (same city, the airport our lanes fly)") if notes else None
