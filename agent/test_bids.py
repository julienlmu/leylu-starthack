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
    carriers = [{"name": f"Air{i}", "email": f"a{i}@x", "kind": "airline", "serves": ["JFK"]} for i in range(6)]
    carriers += [{"name": "Other", "email": "o@x", "kind": "airline", "serves": ["ORD"]},
                 {"name": "Any", "email": "any@x", "kind": "airline", "serves": ["*"]},
                 {"name": "Truck", "email": "t@x", "kind": "trucker", "serves": ["85"]},
                 {"name": "FarTruck", "email": "f@x", "kind": "trucker", "serves": ["20"]}]
    names = [c["name"] for c in carriers_for(carriers, {"destination": "JFK", "pickup": None})]
    assert names == ["Air0", "Air1", "Air2", "Air3", "Air4", "Air5", "Any"]  # every airline serving JFK, no trucker
    with_pickup = carriers_for(carriers, {"destination": "ORD", "pickup": {"address": "Industriestr. 12, 85748 Garching",
                                                                         "zone": None}})
    assert [c["name"] for c in with_pickup] == ["Other", "Any", "Truck"]  # only the trucker serving zone 85
    no_postcode = carriers_for(carriers, {"destination": "ORD", "pickup": {"address": "somewhere", "zone": None}})
    assert [c["name"] for c in no_postcode] == ["Other", "Any"]


def test_the_start_kit_list_loads_and_picks_the_right_carriers():
    from carriers import load_carriers

    kit = load_carriers()  # backend/data/start-kit/carrier-list.csv
    assert len([c for c in kit if c["kind"] == "airline"]) == 29 and len([c for c in kit if c["kind"] == "trucker"]) == 22
    assert all(c["email"].endswith("@hackloop.mail") for c in kit)
    # Email-only destinations (not on the portal) are served by the bid-only airlines.
    assert {c["name"] for c in carriers_for(kit, {"destination": "KTM", "pickup": None})} == {
        "Zephyr Steppe Cargo", "Himalaya Bridge Air", "Pampero Air Cargo"}
    door = carriers_for(kit, {"destination": "MIA", "pickup": {"address": "Leopoldstr. 1, 80802 München", "zone": None}})
    assert [c for c in door if c["kind"] == "trucker"]
    assert all("80" in c["serves"] for c in door if c["kind"] == "trucker")
    assert len([c for c in door if c["kind"] == "airline"]) == 14  # all airlines serving Miami


def test_parse_bid_ignores_our_request_quoted_below_the_reply():
    reply = ("Hi, here is our offer:\nTotal: 1,845.50 EUR\nTransit: 2 days\nRate ID: SKY-8812\n\n"
             "On Sat, 21 Nov 2026, leylu@hackloop.mail wrote:\n> Please reply like this:\n> Total: 1234.00 EUR\n"
             "> Transit: 2 days\n> Rate ID: ABC123")
    assert parse_bid(reply) == {"total": 1845.5, "currency": "EUR", "transit_days": 2.0, "rate_id": "SKY-8812"}


def test_declines_and_amountless_replies_cost_nothing(monkeypatch):
    def no_llm(*a, **kw):
        raise AssertionError("the LLM must not be called")
    monkeypatch.setattr(bids.llm, "chat_json", no_llm)
    for reply in ("Hello, unfortunately we do not serve this lane. Best regards",
                  "We don't serve pickup zone 51, sorry.",
                  "Thanks for asking, we cannot offer this routing at the moment.",
                  "Sorry, no capacity this week."):
        assert bids.read_bid(reply) == (None, 0.0), reply


def test_a_decline_that_still_names_a_price_is_read_by_the_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(bids.llm, "chat_json", lambda *a, **kw: calls.append(1) or (
        {"total": 2450.0, "currency": "EUR", "transit_days": 3.0, "rate_id": None}, 0.00004))
    for reply in ("We cannot offer a direct flight, but via AMS: rate EUR 4.20/kg, total EUR 2,450.00, 3 days.",
                  "We regret the delay. Our offer: air freight EUR 2,100 plus fuel EUR 310, 2 days.",
                  "The Tuesday flight is not available; Thursday works at EUR 1,980 all-in (EUR 1,700 + 280 fees)."):
        assert bids.read_bid(reply)[0] is not None, reply
    assert len(calls) == 3



def test_a_carrier_asking_for_the_postcode_is_an_info_request():
    reply = ("Hello,\n\nthank you for your request. To quote we need:\n- the pickup postcode\n\n"
             "Please reply in this thread.\n\nBest regards\nNeckarstrom Kurier")
    assert bids.info_request(reply) == ["the pickup postcode"]
    assert bids.info_request("Total: 145.00 EUR\nTransit: 1 day\nRate ID: TRK-9") == []
