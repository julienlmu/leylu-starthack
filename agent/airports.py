"""Airports we can price, and the codes customers (or the LLM) use for the same city.

5U's lanes fly from six German airports to ~40 destinations (start-kit carrier list, rate sheets, portal ports). A mail
that says "Tokyo", "New York" or "Shanghai" can come back from the extraction as HND, EWR, NYC or SHA: no lane, no
price, and the round goes to a person. Free, in code: a code we can't price becomes the airport of the same city that we
can price. A code we can price is never changed. AIRPORT_ALIASES=off switches it off.
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
    # German origins: the kit's pickup zones decide (Bremen 28 → HAM, Dortmund 44 → DUS, Hahn 55 → FRA)
    "BRE": "HAM", "KEL": "HAM", "DTM": "DUS", "MGL": "DUS", "ESS": "DUS", "NRN": "DUS", "QDU": "DUS",
    "QKL": "CGN", "BNJ": "CGN", "AGB": "MUC", "HHN": "FRA",
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


def priceable(code: str | None) -> tuple[str | None, str | None]:
    """(code to price with, note) — the note says what was changed, None when nothing was."""
    if not ENABLED or not code:
        return code, None
    plain = code.strip()
    upper = plain.upper()
    lanes = known()
    if not lanes or upper in lanes:
        return (upper if upper in lanes else code), None
    target = SAME_CITY.get(upper) or CITY.get(plain.lower())
    if target and target in lanes:
        return target, f"{code} → {target} (same city, the airport our lanes fly)"
    return code, None
