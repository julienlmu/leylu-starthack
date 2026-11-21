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


def pickup_zone(pickup: dict | None) -> str | None:
    """Two-digit pickup zone from the pickup's zone or its German postcode, or None."""
    if not pickup:
        return None
    zone = str(pickup.get("zone") or "").strip()
    if zone:
        return zone[:2]
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
