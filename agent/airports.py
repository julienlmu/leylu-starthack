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
import re
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

# CITY_NAMES: longer ways to write a city or an airport ("Frankfurt am Main", "Munich Airport (MUC)", "Flughafen
# Düsseldorf", "Chicago O'Hare", "Newark", "Tokyo Haneda"). An airport name gives that airport's own code: one of
# another airport in the city (Newark → EWR, Haneda → HND) is priced first and moved by `aliased` only without a price,
# exactly like the code. CITY_NAMES=off: only the exact city names above.
CITY_NAMES = os.environ.get("CITY_NAMES", "on").lower() != "off"
AIRPORT_NAMES = {
    "haneda": "HND", "narita": "NRT", "newark": "EWR", "la guardia": "LGA", "laguardia": "LGA", "kennedy": "JFK",
    "hongqiao": "SHA", "pudong": "PVG", "daxing": "PKX", "beijing capital": "PEK", "guarulhos": "GRU",
    "viracopos": "VCP", "congonhas": "CGH", "ezeiza": "EZE", "aeroparque": "AEP", "o'hare": "ORD", "ohare": "ORD",
    "o hare": "ORD", "midway": "MDW", "incheon": "ICN", "gimpo": "GMP", "suvarnabhumi": "BKK", "don mueang": "DMK",
    "changi": "SIN", "seletar": "XSP", "al maktoum": "DWC", "dubai world central": "DWC", "pearson": "YYZ",
    "billy bishop": "YTZ", "love field": "DAL", "taoyuan": "TPE", "songshan": "TSA", "chek lap kok": "HKG",
    "jomo kenyatta": "NBO", "o.r. tambo": "JNB", "or tambo": "JNB", "indira gandhi": "DEL",
    "chhatrapati shivaji": "BOM", "king khalid": "RUH", "ben gurion": "TLV", "tullamarine": "MEL",
    "kingsford smith": "SYD", "noi bai": "HAN", "tan son nhat": "SGN", "ninoy aquino": "MNL", "jorge chavez": "LIM",
    "jorge chávez": "LIM", "el dorado": "BOG", "arturo merino": "SCL", "hamad": "DOH", "murtala": "LOS",
    "hartsfield": "ATL", "konrad adenauer": "CGN", "franz josef strauss": "MUC", "franz josef strauß": "MUC",
}
NAME_FILLER = re.compile(r"\b(?:international|intl\.?|int'l|airport|flughafen|aéroport|aeroporto|aeropuerto|luchthaven|"
                         r"lotnisko|havalimanı|am main|cargo|city|germany|deutschland)\b|[()\[\],.;/]", re.I)

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


# AIRPORT_TYPOS: "fra" → FRA, ICAO codes (EDDF → FRA, KORD → ORD) and a misspelt city ("Frankfrut", "Munchen",
# "Chicgo") → the airport our lanes fly. A misspelt 3-letter code is never guessed (MCU could be a real airport).
AIRPORT_TYPOS = os.environ.get("AIRPORT_TYPOS", "on").lower() != "off"
ICAO = {"SGAS": "ASU", "KATL": "ATL", "VTBS": "BKK", "SKBO": "BOG", "VABB": "BOM", "HECA": "CAI", "EDDK": "CGN",
        "VIDP": "DEL", "KDFW": "DFW", "OTHH": "DOH", "EDDL": "DUS", "OMDB": "DXB", "SAEZ": "EZE", "EDDF": "FRA",
        "SBGR": "GRU", "EDDH": "HAM", "VHHH": "HKG", "RKSI": "ICN", "KJFK": "JFK", "FAOR": "JNB", "VNKT": "KTM",
        "WMKK": "KUL", "KLAX": "LAX", "SPJC": "LIM", "SPIM": "LIM", "DNMM": "LOS", "YMML": "MEL", "MMMX": "MEX",
        "KMIA": "MIA", "RPLL": "MNL", "EDDM": "MUC", "HKJK": "NBO", "RJAA": "NRT", "KORD": "ORD", "NTAA": "PPT",
        "ZBAA": "PEK", "ZSPD": "PVG", "OERK": "RUH", "SCEL": "SCL", "VVTS": "SGN", "WSSS": "SIN", "EDDS": "STR",
        "YSSY": "SYD", "LLBG": "TLV", "FMMI": "TNR", "RCTP": "TPE", "ZMUB": "ULN", "ZMCK": "ULN", "CYYZ": "YYZ"}


def _fold(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def _typo(value: str) -> str | None:
    """The airport of the one city name `value` is a near-miss of (two letters off at most), else None."""
    import difflib
    cleaned = _fold(" ".join(NAME_FILLER.sub(" ", value.lower().replace("-", " ")).split()))
    if len(cleaned) < 5:
        return None
    names = {_fold(city): code for city, code in CITY.items() if code in known() and len(city) >= 5}
    close = difflib.get_close_matches(cleaned, list(names), n=3, cutoff=0.85)  # "Atlantis" (0.80) is no Atlanta
    # a letter dropped, added or swapped is a typo; a letter replaced is often another real town ("Homburg" ≠ Hamburg)
    codes = {names[c] for c in close if len(c) != len(cleaned) or sorted(c) == sorted(cleaned)}
    return codes.pop() if len(codes) == 1 else None


def city_code(value: str | None) -> tuple[str | None, str | None]:
    """A city name the extraction returned instead of a code → (its airport, note). Codes are never changed here
    (AIRPORT_TYPOS: except "fra" → FRA and an ICAO code of an airport we fly)."""
    if not ENABLED or not value:
        return value, None
    plain = value.strip()
    if AIRPORT_TYPOS and len(plain) == 3 and plain.isalpha() and plain.islower() and plain.upper() in known():
        return plain.upper(), f"{value} → {plain.upper()}"
    if AIRPORT_TYPOS and plain.upper() in ICAO and ICAO[plain.upper()] in known():
        return ICAO[plain.upper()], f"{value} → {ICAO[plain.upper()]} (ICAO code)"
    if len(plain) == 3 and plain.isalpha():
        return value, None
    target = CITY.get(plain.lower())
    if target and target in known():
        return target, f"{value} → {target}"
    if CITY_NAMES and (target := _named(value)):
        return target, f"{value} → {target}"
    if AIRPORT_TYPOS and (target := _typo(value)):
        return target, f"{value} → {target} (spelling)"
    return value, None


def _named(value: str) -> str | None:
    """The code in a longer airport or city name, or None: a code in it first, then an airport name, then a city."""
    for code in re.findall(r"\b([A-Z]{3})\b", value):  # "Munich Airport (MUC)", "MUC airport", "New York JFK"
        if code in known() or code in SAME_CITY:
            return code
    plain = " ".join(value.lower().replace("-", " ").split())
    for name, code in AIRPORT_NAMES.items():
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", plain) and (code in known() or code in SAME_CITY):
            return code
    cleaned = " ".join(NAME_FILLER.sub(" ", plain).split())
    if (code := CITY.get(cleaned)) and code in known():
        return code
    hits = [city for city in CITY if re.match(rf"{re.escape(city)}(?!\w)", cleaned) and CITY[city] in known()]
    return CITY[max(hits, key=len)] if hits else None  # "New York, USA" → JFK; only a name the value starts with


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
