"""Carrier list: who to ask for bids.

Default: the start kit's list, backend/data/start-kit/carrier-list.csv (name,kind,email,serves). Airlines serve
destination airports; truckers serve pickup zones, the first two digits of a German postcode, the same rule as the
backend's pickup zones (backend/tariffs.py). CARRIERS_FILE may point to another CSV or to a JSON list of
{"name", "email", "kind", "serves"} (tests, or no-carriers.json to switch bids off).
"""

import csv
import json
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


def carriers_for(carriers: list[dict], rfq: dict) -> list[dict]:
    """Airlines that serve the destination, plus for door-to-port the truckers that serve the pickup zone."""
    airlines = [c for c in carriers if c["kind"] == "airline"
                and (rfq["destination"] in c["serves"] or "*" in c["serves"])]
    zone = pickup_zone(rfq.get("pickup"))
    truckers = [c for c in carriers if c["kind"] == "trucker" and zone in c["serves"]] if zone else []
    return airlines[:MAX_AIRLINES] + truckers
