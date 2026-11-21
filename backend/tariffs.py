"""Tariffs as structured prices: airline rate sheets (start kit + ingested monthly tariffs) and the pickup-zone map.

A sheet is {airline, currency, breaks_kg, valid_from, valid_to, cbm_kg, lanes: [{lane "MUC-JFK", transit_days,
minimum, rates (one per break), fuel, security}]}, the shape of data/tariffs.json (all 10 start-kit sheets).
"""

import csv
import json
import re
from pathlib import Path

DATA = Path(__file__).parent / "data"
POSTCODE = re.compile(r"\b(\d{5})\b")


class Tariffs:
    def __init__(self, sheets: list[dict] | None = None):
        self.sheets: list[dict] = []
        for sheet in sheets or []:
            self.add(sheet)

    @classmethod
    def from_files(cls, *paths: Path) -> "Tariffs":
        tariffs = cls()
        for path in paths:
            if not path.exists():
                continue
            try:
                sheets = json.loads(path.read_text())["sheets"]
            except (ValueError, KeyError, TypeError) as error:  # e.g. a save cut off by a restart
                print(f"tariffs: skipped unreadable {path.name}: {error}")
                continue
            for sheet in sheets:
                tariffs.add(sheet)
        return tariffs

    def add(self, sheet: dict) -> int:
        """Adds a sheet; it replaces an older sheet of the same airline with the same validity. Returns its lane count."""
        self.sheets = [s for s in self.sheets
                       if not (s["airline"] == sheet["airline"] and s["valid_from"] == sheet["valid_from"])]
        self.sheets.append(sheet)
        return len(sheet["lanes"])

    def lanes(self, origin: str, destination: str, date: str) -> list[tuple[dict, dict]]:
        """(sheet, lane) per airline flying origin-destination, from that airline's newest sheet valid on `date`."""
        key = f"{origin}-{destination}".upper()
        best: dict[str, tuple[dict, dict]] = {}
        for sheet in self.sheets:
            if not (sheet["valid_from"] <= date <= sheet["valid_to"]):
                continue
            for lane in sheet["lanes"]:
                if lane["lane"].upper() == key:
                    held = best.get(sheet["airline"])
                    if held is None or sheet["valid_from"] > held[0]["valid_from"]:
                        best[sheet["airline"]] = (sheet, lane)
        return list(best.values())


class Zones:
    """Pickup zones: the first two digits of a German postcode → area and origin airport. No prices (truckers bid)."""

    def __init__(self, path: Path = DATA / "pickup_zones.csv"):
        with path.open() as f:
            self.zones = {row["zone"]: row for row in csv.DictReader(f)}

    def resolve(self, pickup: dict | None) -> dict | None:
        """{zone, area, airport} for a pickup ({address, zone}), or None if the zone can't be told."""
        if not pickup:
            return None
        zone = str(pickup.get("zone") or "").strip()
        if zone not in self.zones:
            match = POSTCODE.search(pickup.get("address") or "")
            zone = match.group(1)[:2] if match else ""
        return dict(self.zones[zone]) if zone in self.zones else None
