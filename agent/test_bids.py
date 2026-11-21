import pytest

import bids
from bids import parse_bid, read_bid, to_number
from carriers import carriers_for


@pytest.mark.parametrize("text, expected", [
    ("1,234.50", 1234.5), ("1.234,50", 1234.5), ("1234,5", 1234.5), ("1.234", 1234.0),
    ("980", 980.0), ("1,234", 1234.0), ("12.5", 12.5),
])
def test_to_number(text, expected):
    assert to_number(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Total: 1,234.50 EUR\nTransit: 2 days\nRate ID: SKY-123",
     {"total": 1234.5, "currency": "EUR", "transit_days": 2.0, "rate_id": "SKY-123"}),
    ("Gesamtpreis 1.234,50 € all-in, Laufzeit 48 Stunden. Rate-ID: LH/778",
     {"total": 1234.5, "currency": "EUR", "transit_days": 2.0, "rate_id": "LH/778"}),
    ("We can do EUR 980 for this one.",
     {"total": 980.0, "currency": "EUR", "transit_days": None, "rate_id": None}),
    ("Freight 900 EUR plus fuel 120 EUR", None),  # two amounts and no total: leave it to the LLM
    ("Sorry, no capacity this week.", None),
])
def test_parse_bid(text, expected):
    assert parse_bid(text) == expected


def test_read_bid_falls_back_to_the_llm_only_when_regexes_fail(monkeypatch):
    calls = []

    def fake_chat_json(name, system, user, schema):
        calls.append(name)
        return {"total": 1020.0, "currency": "EUR", "transit_days": 3, "rate_id": None}, 0.00005

    monkeypatch.setattr(bids.llm, "chat_json", fake_chat_json)
    assert read_bid("Total: 900.00 EUR") == ({"total": 900.0, "currency": "EUR", "transit_days": None,
                                              "rate_id": None}, 0.0)
    assert read_bid("Freight 900 EUR plus fuel 120 EUR")[1] == 0.00005
    assert calls == ["bid"]


def test_carriers_for_picks_destination_airlines_and_truckers_only_for_pickup():
    carriers = [{"name": f"Air{i}", "email": f"a{i}@x", "kind": "airline", "destinations": ["JFK"]} for i in range(6)]
    carriers += [{"name": "Other", "email": "o@x", "kind": "airline", "destinations": ["ORD"]},
                 {"name": "Any", "email": "any@x", "kind": "airline", "destinations": ["*"]},
                 {"name": "Truck", "email": "t@x", "kind": "trucker", "destinations": []}]
    names = [c["name"] for c in carriers_for(carriers, {"destination": "JFK", "pickup": None})]
    assert names == ["Air0", "Air1", "Air2", "Air3", "Air4"]
    with_pickup = carriers_for(carriers, {"destination": "ORD", "pickup": {"address": "…", "zone": None}})
    assert [c["name"] for c in with_pickup] == ["Other", "Any", "Truck"]


def test_parse_bid_ignores_our_request_quoted_below_the_reply():
    reply = ("Hi, here is our offer:\nTotal: 1,845.50 EUR\nTransit: 2 days\nRate ID: SKY-8812\n\n"
             "On Sat, 21 Nov 2026, leylu@hackloop.mail wrote:\n> Please reply like this:\n> Total: 1234.00 EUR\n"
             "> Transit: 2 days\n> Rate ID: ABC123")
    assert parse_bid(reply) == {"total": 1845.5, "currency": "EUR", "transit_days": 2.0, "rate_id": "SKY-8812"}
