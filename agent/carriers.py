"""Carrier list: who to ask for bids.

Default: the start kit's list, backend/data/start-kit/carrier-list.csv (name,kind,email,serves). Airlines serve
destination airports; truckers serve pickup zones, the first two digits of a German postcode, the same rule as the
backend's pickup zones (backend/tariffs.py). CARRIERS_FILE may point to another CSV or to a JSON list of
{"name", "email", "kind", "serves"} (tests, or no-carriers.json to switch bids off).
"""

import csv
import json
import os
import re
from pathlib import Path

KIT_LIST = Path(__file__).resolve().parent.parent / "backend" / "data" / "start-kit" / "carrier-list.csv"
# The brief: only 2-5 carriers per destination answer, and we don't know which, so we ask every airline that serves
# it (Miami has 14). The cap only guards against a broken list; 5U allows 60 sends per minute.
MAX_AIRLINES = 15
POSTCODE = re.compile(r"\b(\d{5})\b")


def load_carriers(path: str | Path = KIT_LIST) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    if path.suffix.lower() == ".csv":
        with path.open(newline="") as f:
            return [{"name": row["name"].strip(), "kind": row["kind"].strip(), "email": row["email"].strip().lower(),
                     "serves": row["serves"].split()} for row in csv.DictReader(f)]
    return json.loads(path.read_text())


# FOREIGN_PICKUP: a pickup our 32 zones don't cover gets the nearest zone's truckers and airport instead of no pickup leg
# (a door-to-port quote without its truck is held, then priced too low). A German postcode outside the zones (Berlin 10,
# Leipzig 04, Nürnberg 90) → the zone nearest by road; Austria / Switzerland / the Netherlands / Belgium / Luxembourg /
# Denmark / Czechia (named, or "A-6020", "CH-8001", "NL-1012", "1012 AB") → the zone next to that border. Any other
# country stays unknown (no guess). off = as before.
FOREIGN_PICKUP = os.environ.get("FOREIGN_PICKUP", "on").lower() != "off"
ZONES_FILE = Path(__file__).resolve().parent.parent / "backend" / "data" / "pickup_zones.csv"
NEAREST = {  # German 2-digit postcode areas without a zone → nearest zone (by road to the zone's airport)
    "01": "93", "02": "93", "03": "20", "04": "36", "06": "36", "07": "93", "08": "93", "09": "93",
    "10": "20", "12": "20", "13": "20", "14": "20", "15": "20", "16": "20", "17": "20", "18": "20", "19": "20",
    "23": "22", "25": "24", "26": "28", "27": "28", "29": "21", "30": "21", "31": "21", "32": "44", "33": "44",
    "34": "35", "37": "36", "38": "21", "39": "21", "46": "47", "48": "44", "49": "44", "52": "50", "54": "53",
    "56": "53", "57": "51", "58": "44", "59": "44", "66": "55", "67": "64", "68": "64", "69": "64", "74": "71",
    "75": "71", "76": "70", "77": "72", "78": "72", "79": "72", "82": "81", "83": "81", "87": "86", "88": "73",
    "89": "73", "90": "93", "91": "93", "92": "93", "94": "84", "95": "93", "96": "93", "97": "63", "98": "36", "99": "36",
}
COUNTRY_ZONE = (  # (pattern, zone, country)
    (re.compile(r"\b(?:austria|österreich|oesterreich|autriche)\b|(?<![\w-])A-\d{4}\b", re.I), "80", "Austria"),
    (re.compile(r"\b(?:switzerland|schweiz|suisse|svizzera)\b|(?<![\w-])CH-\d{4}\b", re.I), "70", "Switzerland"),
    (re.compile(r"(?i:\b(?:netherlands|nederland|niederlande|holland|pays-bas)\b)|(?<![\w-])NL-\d{4}|\b\d{4}\s?[A-Z]{2}\b"),
     "40", "the Netherlands"),
    (re.compile(r"\b(?:belgium|belgien|belgique|belgië)\b|(?<![\w-])B-\d{4}\b", re.I), "50", "Belgium"),
    (re.compile(r"\b(?:luxembourg|luxemburg)\b|(?<![\w-])L-\d{4}\b", re.I), "55", "Luxembourg"),
    (re.compile(r"\b(?:denmark|dänemark|danmark)\b|(?<![\w-])DK-\d{4}\b", re.I), "24", "Denmark"),
    (re.compile(r"\b(?:czech\s+republic|czechia|tschechien|česko)\b|(?<![\w-])CZ-\d{3}", re.I), "93", "Czechia"),
)
# another country named: a 5-digit number there is no German postcode (Paris 75001, Milano 20121)
OTHER_COUNTRY = re.compile(r"\b(?:france|frankreich|poland|polen|polska|ital(?:y|ien|ia)|spa(?:in|nien)|españa|portugal|"
                           r"united\s+kingdom|england|great\s+britain|uk|usa|united\s+states|sweden|schweden|norway|"
                           r"norwegen|finland|hungary|ungarn|slovakia|slowakei|slovenia|croatia|romania|bulgaria|greece|"
                           r"turkey|türkei|türkiye|china|india|mexico|brazil|canada)\b", re.I)
_KNOWN: set[str] = set()


def known_zones() -> set[str]:
    if not _KNOWN and ZONES_FILE.exists():
        with ZONES_FILE.open(newline="") as f:
            _KNOWN.update(row["zone"] for row in csv.DictReader(f))
    return _KNOWN


def nearest_zone(address: str | None) -> tuple[str, str] | None:
    """(zone, why) for a pickup outside our zones, or None: a known zone, an unknown country or no clue."""
    if not (FOREIGN_PICKUP and address):
        return None
    for pattern, zone, country in COUNTRY_ZONE:
        if pattern.search(address):
            return zone, f"pickup in {country}: nearest zone {zone}"
    match = POSTCODE.search(address)
    if match and not OTHER_COUNTRY.search(address) and match.group(1)[:2] not in known_zones() and (zone := NEAREST.get(match.group(1)[:2])):
        return zone, f"postcode {match.group(1)} is outside our zones: nearest zone {zone}"
    return None


def pickup_zone(pickup: dict | None) -> str | None:
    """Two-digit pickup zone from the pickup's zone or its German postcode (nearest zone outside ours), or None."""
    if not pickup:
        return None
    zone = str(pickup.get("zone") or "").strip()
    if zone:
        return zone[:2]
    if near := nearest_zone(pickup.get("address")):
        return near[0]
    if FOREIGN_PICKUP and OTHER_COUNTRY.search(pickup.get("address") or ""):
        return None  # Milano 20121 is no Hamburg zone 20
    match = POSTCODE.search(pickup.get("address") or "")
    return match.group(1)[:2] if match else None


# A destination no airline on the list serves (a lane 5U adds later, priced only by email bids): ask every airline once
# instead of nobody. Not for a city we price under another code (HND → NRT, airports.aliased): that one is priced there.
NEW_LANE_ASK_ALL = os.environ.get("NEW_LANE_ASK_ALL", "on").lower() != "off"
MAX_NEW_LANE_AIRLINES = 30  # the kit list has 29; 5U allows 60 sends per minute


def carriers_for(carriers: list[dict], rfq: dict) -> list[dict]:
    """Airlines that serve the destination, plus for door-to-port the truckers that serve the pickup zone."""
    airlines = [c for c in carriers if c["kind"] == "airline"
                and (rfq["destination"] in c["serves"] or "*" in c["serves"])]
    if not airlines and _new_lane(rfq):
        airlines = [c for c in carriers if c["kind"] == "airline"][:MAX_NEW_LANE_AIRLINES]
        zone = pickup_zone(rfq.get("pickup"))
        truckers = [c for c in carriers if c["kind"] == "trucker" and zone in c["serves"]] if zone else []
        return airlines + truckers
    zone = pickup_zone(rfq.get("pickup"))
    truckers = [c for c in carriers if c["kind"] == "trucker" and zone in c["serves"]] if zone else []
    return airlines[:MAX_AIRLINES] + truckers


def _new_lane(rfq: dict) -> bool:
    destination = (rfq.get("destination") or "").strip().upper()
    if not (NEW_LANE_ASK_ALL and re.fullmatch(r"[A-Z]{3}", destination)):
        return False
    from airports import aliased  # here, not at the top: airports reads the same kit list
    return aliased({**rfq, "destination": destination}) is None
