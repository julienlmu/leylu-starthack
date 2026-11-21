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
    ("Freight 900 EUR plus fuel 120 EUR",  # a surcharge on top is added in code, no LLM
     {"total": 1020.0, "currency": "EUR", "transit_days": None, "rate_id": None}),
    ("Freight 900 EUR, insurance 120 EUR", None),  # two amounts and no total: leave it to the LLM
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
    assert read_bid("Freight 900 EUR, insurance 120 EUR")[1] == 0.00005
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


def test_a_decline_that_still_names_a_price_is_still_read(monkeypatch):
    monkeypatch.setattr(bids.llm, "chat_json", lambda *a, **kw: (
        {"total": 2450.0, "currency": "EUR", "transit_days": 3.0, "rate_id": None}, 0.00004))
    for reply, total in (("We cannot offer a direct flight, but via AMS: rate EUR 4.20/kg, total EUR 2,450.00, 3 days.",
                          2450.0),
                         ("We regret the delay. Our offer: air freight EUR 2,100 plus fuel EUR 310, 2 days.", 2410.0),
                         ("The Tuesday flight is not available; Thursday works at EUR 1,980 all-in (EUR 1,700 + 280 "
                          "fees).", 1980.0)):
        bid, _ = bids.read_bid(reply)
        assert bid is not None and bid["total"] == total, reply


# Carriers that answer in their own shape instead of "Total: 1234.00 EUR" (likely after an hourly change).
# 1,000 kg chargeable unless the case says otherwise.
@pytest.mark.parametrize("reply, total", [
    # per-kg rate is never the total: 2.35 would win the pick and get the quote rejected too_low
    ("Our rate: EUR 2.35/kg all-in.", 2350.0),
    ("Rate EUR 2.35 per kg, minimum EUR 150.", 2350.0),
    ("Rate EUR 0.10 per kg, minimum charge EUR 150.", 150.0),
    ("Rate: 2,35 €/kg + fuel 0,85 €/kg + security 0,15 €/kg", 3350.0),
    # flat price with per-kg surcharges on top
    ("Price: EUR 1,850.00 excl. fuel surcharge EUR 0.85/kg and security EUR 0.15/kg. Transit 2 days.", 2850.0),
    ("Angebot: 1.850,00 EUR zzgl. Treibstoffzuschlag 0,85 EUR/kg", 2700.0),
    # flat surcharges on top, no total line
    ("Air freight: EUR 1,850.00\nFuel surcharge: EUR 240.00\nSecurity: EUR 60.00", 2150.0),
    # an all-in total with per-kg or surcharge info next to it: the total wins
    ("Total: EUR 2,450.00 all-in (EUR 2.45/kg incl. fuel and security)", 2450.0),
    ("Total: 2,150.00 EUR\nincluding fuel surcharge EUR 240", 2150.0),
    ("Total: 1,234.50 EUR\nTransit: 2 days\nRate ID: SKY-123", 1234.5),
    # per-kg surcharges on their own lines are charged on top (review of #84)
    ("Freight EUR 1,200\nFuel EUR 0.85/kg\nSecurity EUR 0.15/kg", 2200.0),
])
def test_carrier_offers_in_other_shapes_become_one_all_in_total(reply, total):
    bid = parse_bid(reply, 1000.0)
    assert bid is not None and bid["total"] == total, reply


def test_a_per_kg_offer_without_the_weight_is_never_a_total(monkeypatch):
    assert parse_bid("Our rate: EUR 2.35/kg all-in.") is None
    assert parse_bid("Price: EUR 1,850 excl. fuel EUR 0.85/kg") is None



def test_a_carrier_asking_for_the_postcode_is_an_info_request():
    reply = ("Hello,\n\nthank you for your request. To quote we need:\n- the pickup postcode\n\n"
             "Please reply in this thread.\n\nBest regards\nNeckarstrom Kurier")
    assert bids.info_request(reply) == ["the pickup postcode"]
    assert bids.info_request("Total: 145.00 EUR\nTransit: 1 day\nRate ID: TRK-9") == []


def test_a_bid_that_says_please_let_us_know_is_still_a_bid():
    for reply in ("Total: 145.00 EUR\nTransit: 1 day\nRate ID: TRK-9\n\nPlease let us know if you'd like to book.",
                  "Our price is EUR 210 all-in, pickup tomorrow. Please send the booking to dispo@x.example"):
        assert bids.info_request(reply) == [], reply


def test_bid_shapes_off_reads_exactly_as_before(monkeypatch):
    monkeypatch.setattr(bids, "BID_SHAPES", False)
    assert parse_bid("Freight 900 EUR plus fuel 120 EUR", 1000.0) is None  # old: two amounts → LLM
    assert parse_bid("Our rate: EUR 2.35/kg all-in.", 1000.0)["total"] == 2.35  # old reading (the floor drops it)
    assert parse_bid("Total: 1,234.50 EUR", 1000.0)["total"] == 1234.5


@pytest.mark.parametrize("reply", [
    "Total: 1,234.50 EUR\nTransit: 2 days\nRate ID: SKY-123",
    "Gesamtpreis 1.234,50 € all-in, Laufzeit 48 Stunden. Rate-ID: LH/778",
    "We can do EUR 980 for this one.",
    "Total: 145.00 EUR\nTransit: 1 day\nRate ID: TRK-9\n\nPlease let us know if you'd like to book.",
    "Total: 2,150.00 EUR\nincluding fuel surcharge EUR 240",
    "Total: 145.00 EUR\nPlus EUR 30 for a tail-lift if needed",
])
def test_replies_the_old_reading_got_right_are_unchanged(reply, monkeypatch):
    new = parse_bid(reply, 1000.0)
    monkeypatch.setattr(bids, "BID_SHAPES", False)
    assert new == parse_bid(reply, 1000.0)


@pytest.mark.parametrize("reply", [
    "EUR 1,850 incl. fuel EUR 240",  # included: adding it would count it twice
    "Price EUR 1,850 (fuel EUR 0.85/kg included)",
    "Freight EUR 1,850, rate EUR 1.85/kg",  # a flat price next to a per-kg rate: unclear
    "45+ kg EUR 3.10/kg, 100+ kg EUR 2.80/kg",  # two per-kg rates: unclear
    "Freight 900 EUR, insurance 120 EUR",  # two prices, the second not a surcharge
    "EUR 1,850 for the 1000 kg, plus EUR 1,600 for the return leg (optional)",  # optional: not in the price
    "Air freight EUR 1,850 plus fuel EUR 240, insurance EUR 120 on request",
])
def test_ambiguous_offers_are_left_to_the_llm(reply):
    assert bids._code_total(bids.latest_text(reply), 1000.0) is None
    assert parse_bid(reply, 1000.0) is None
