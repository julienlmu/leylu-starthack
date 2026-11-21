import carriers
from carriers import KIT_LIST, carriers_for, load_carriers

KIT = load_carriers(KIT_LIST)
AIRLINES = [c for c in KIT if c["kind"] == "airline"]


def _airlines(rfq):
    return [c["name"] for c in carriers_for(KIT, rfq) if c["kind"] == "airline"]


def test_a_destination_nobody_serves_asks_every_airline_once():
    assert _airlines({"destination": "AKL", "pickup": None}) == [c["name"] for c in AIRLINES]
    with_pickup = carriers_for(KIT, {"destination": "AKL", "pickup": {"address": "Industriestr. 12, 85748 Garching"}})
    assert any(c["kind"] == "trucker" for c in with_pickup)  # the trucker leg is still asked


def test_served_destinations_and_cities_we_price_elsewhere_are_unchanged(monkeypatch):
    served = _airlines({"destination": "JFK", "pickup": None})
    assert served and len(served) < len(AIRLINES)
    assert _airlines({"destination": "HND", "pickup": None}) == []  # priced at NRT (airports.aliased), nobody spammed
    assert _airlines({"destination": None, "pickup": None}) == []
    assert _airlines({"destination": "Tokyo", "pickup": None}) == []
    monkeypatch.setattr(carriers, "NEW_LANE_ASK_ALL", False)
    assert _airlines({"destination": "AKL", "pickup": None}) == []  # off: as before
