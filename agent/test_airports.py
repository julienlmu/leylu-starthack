import pytest

import airports
import extract as extract_mod
import rfq_agent
from bids import BidBoard
from extract import to_rfq
from inbox import FixtureMailbox
from test_rfq_agent import MAIL, OPTION, RAW, FakeApi


@pytest.mark.parametrize("code, expected", [
    ("HND", "NRT"), ("TYO", "NRT"), ("EWR", "JFK"), ("NYC", "JFK"), ("LGA", "JFK"), ("SHA", "PVG"), ("PKX", "PEK"),
    ("VCP", "GRU"), ("AEP", "EZE"), ("GMP", "ICN"), ("DMK", "BKK"), ("MDW", "ORD"), ("YTZ", "YYZ"), ("UBN", "ULN"),
    ("hnd", "NRT"),
])
def test_the_same_citys_airport_is_offered_for_a_destination_without_lanes(code, expected):
    alias, note = airports.aliased({"origin": "MUC", "destination": code})
    assert alias == {"origin": "MUC", "destination": expected} and expected in note


@pytest.mark.parametrize("origin, expected", [("BRE", "HAM"), ("DTM", "DUS"), ("HHN", "FRA")])
def test_german_airports_without_lanes_offer_the_kits_pickup_zone_airport(origin, expected):
    assert airports.aliased({"origin": origin, "destination": "JFK"})[0]["origin"] == expected


@pytest.mark.parametrize("code", ["JFK", "NRT", "PVG", "LOS", "ULN", "LHR", "BER", "NUE", "XYZ", None, ""])
def test_no_alias_for_priced_airports_or_cities_we_do_not_serve(code):
    assert airports.aliased({"origin": "MUC", "destination": code}) is None


@pytest.mark.parametrize("name, expected", [("Tokyo", "NRT"), ("New York", "JFK"), ("São Paulo", "GRU"),
                                            ("Munich", "MUC"), ("HND", "HND"), ("JFK", "JFK"), ("Atlantis", "Atlantis")])
def test_city_names_become_codes_but_codes_stay_as_extracted(name, expected):
    assert airports.city_code(name)[0] == expected


def test_the_known_airports_come_from_the_kit_data():
    lanes = airports.known()
    assert {"CGN", "DUS", "FRA", "HAM", "MUC", "STR"} <= lanes and {"JFK", "NRT", "PVG", "SGN", "ULN"} <= lanes
    assert set(airports.SAME_CITY.values()) <= lanes  # every alias points at a priced airport


def test_to_rfq_keeps_codes_and_turns_city_names_into_codes():
    raw = {**RAW, "origin": "MUC", "destination": "HND", "pickup_address": None}
    assert to_rfq(raw)[0]["destination"] == "HND"  # priced first as extracted: the portal's lanes change
    rfq, missing = to_rfq({**raw, "destination": "Tokyo"})
    assert rfq["destination"] == "NRT" and "Tokyo" in rfq["airport_note"] and missing == []


class LanesApi(FakeApi):
    """Prices only the lanes in `priced`."""

    def __init__(self, priced):
        super().__init__({"options": [OPTION], "chosen": OPTION})
        self.priced, self.asked = priced, []

    def price(self, rfq, bids=None, fallback=False):
        self.asked.append(rfq["destination"])
        if rfq["destination"] in self.priced:
            return {"options": [OPTION], "chosen": OPTION, "why": "cheapest"}
        return {"options": [], "chosen": None, "why": "no lane"}


def _quote(tmp_path, monkeypatch, priced):
    raw = {**RAW, "destination": "HND", "pickup_address": None}
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)  # no person steps in: don't wait 100 s in a test
    box, api = FixtureMailbox(tmp_path), LanesApi(priced)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0.1)
    return box, api


def test_no_price_at_hnd_is_priced_at_nrt_and_quoted(tmp_path, monkeypatch):
    box, api = _quote(tmp_path, monkeypatch, {"NRT"})
    assert api.asked == ["HND", "NRT"] and "quote_sent" in api.events and box.sent[-1]["thread_id"] == "t1"
    assert any(u.get("rfq", {}).get("destination") == "NRT" for u in api.updates)


def test_a_priced_hnd_is_quoted_as_hnd(tmp_path, monkeypatch):
    box, api = _quote(tmp_path, monkeypatch, {"HND", "NRT"})
    assert api.asked == ["HND"] and "quote_sent" in api.events


def test_airport_aliases_off(tmp_path, monkeypatch):
    monkeypatch.setattr(airports, "ENABLED", False)
    assert airports.aliased({"origin": "MUC", "destination": "HND"}) is None
    assert airports.city_code("Tokyo") == ("Tokyo", None)
    box, api = _quote(tmp_path, monkeypatch, {"NRT"})
    assert api.asked[0] == "HND" and "NRT" not in api.asked and "quote_sent" not in api.events
