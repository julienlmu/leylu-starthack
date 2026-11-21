import pytest

import airports
from extract import to_rfq
from test_rfq_agent import RAW


@pytest.mark.parametrize("code, expected", [
    ("HND", "NRT"), ("TYO", "NRT"), ("EWR", "JFK"), ("NYC", "JFK"), ("LGA", "JFK"), ("SHA", "PVG"), ("PKX", "PEK"),
    ("VCP", "GRU"), ("AEP", "EZE"), ("GMP", "ICN"), ("DMK", "BKK"), ("MDW", "ORD"), ("YTZ", "YYZ"), ("UBN", "ULN"),
    ("Tokyo", "NRT"), ("New York", "JFK"), ("São Paulo", "GRU"), ("Munich", "MUC"), ("hkg", "HKG"),
    ("BRE", "HAM"), ("DTM", "DUS"), ("HHN", "FRA"),  # German airports without lanes → the kit's pickup-zone airport
])
def test_a_code_we_cannot_price_becomes_the_airport_of_the_same_city(code, expected):
    assert airports.priceable(code)[0] == expected


@pytest.mark.parametrize("code", ["JFK", "NRT", "PVG", "MUC", "FRA", "CGN", "LOS", "ULN", None, ""])
def test_a_code_we_price_is_never_changed(code):
    assert airports.priceable(code) == (code, None)


@pytest.mark.parametrize("code", ["LHR", "CDG", "BER", "NUE", "XYZ", "Atlantis"])
def test_a_city_we_do_not_serve_stays_as_it_is(code):
    assert airports.priceable(code) == (code, None)  # no lane anywhere: a person decides, as before


def test_the_known_airports_come_from_the_kit_data():
    lanes = airports.known()
    assert {"CGN", "DUS", "FRA", "HAM", "MUC", "STR"} <= lanes and {"JFK", "NRT", "PVG", "SGN", "ULN"} <= lanes
    assert {target for target in airports.SAME_CITY.values()} <= lanes  # every alias points at a priced airport


def test_to_rfq_prices_the_extracted_city_code_and_notes_it():
    raw = {**RAW, "origin": "MUC", "destination": "HND", "pickup_address": None}
    rfq, missing = to_rfq(raw)
    assert rfq["destination"] == "NRT" and "HND" in rfq["airport_note"] and missing == []
    rfq, _ = to_rfq({**raw, "destination": "NRT"})
    assert rfq["destination"] == "NRT" and "airport_note" not in rfq


def test_airport_aliases_off(monkeypatch):
    monkeypatch.setattr(airports, "ENABLED", False)
    assert airports.priceable("HND") == ("HND", None)
