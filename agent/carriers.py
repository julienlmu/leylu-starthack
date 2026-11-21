"""Carrier list: who to ask for bids.

shortcut: our own JSON format until the start-kit carrier list arrives (U1), then convert it to this:
[{"name": "SkyAir", "email": "bids@skyair.example", "kind": "airline" | "trucker", "destinations": ["JFK"] or ["*"]}]
"""

import json
from pathlib import Path

MAX_AIRLINES = 5


def load_carriers(path: str | Path) -> list[dict]:
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else []


def carriers_for(carriers: list[dict], rfq: dict) -> list[dict]:
    """Airlines that serve the destination, plus truckers when the customer wants pickup (door-to-port)."""
    airlines = [c for c in carriers if c["kind"] == "airline"
                and (rfq["destination"] in c["destinations"] or "*" in c["destinations"])]
    truckers = [c for c in carriers if c["kind"] == "trucker"] if rfq.get("pickup") else []
    return airlines[:MAX_AIRLINES] + truckers
