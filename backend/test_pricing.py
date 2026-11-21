import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from portal import Portal
from pricing import Pricer, choose, sheet_option, weights
from tariffs import DATA, Tariffs, Zones

TARIFFS = Tariffs.from_files(DATA / "tariffs.json")


def rfq(origin, destination, kg, cbm, ask="cheapest", pickup=None, ready="2026-11-23"):
    return {"origin": origin, "destination": destination, "ask": ask, "pickup": pickup, "ready_date": ready,
            "pieces": [{"count": 1, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": kg}],
            "volume_m3": cbm}


def lane(airline, key):
    return next((s, l) for s in TARIFFS.sheets if s["airline"] == airline for l in s["lanes"] if l["lane"] == key)


def offline_pricer() -> Pricer:
    return Pricer(TARIFFS, Zones(), Portal(api_key=""))  # no key: no portal rates, lanes from the kit snapshot


def price(pricer, request, bids=()):
    return asyncio.run(pricer.price(request, list(bids)))


# --- the worked examples in docs/KIT_SUMMARY.md §6 ---
def test_minimum_binds_and_surcharges_stay_per_kg():
    option = sheet_option(*lane("Vega Skyfreight", "MUC-ORD"), 40, 0.1)
    assert option["total"] == 199.36 and option["billed_weight_kg"] == 40
    assert option["breakdown"][0]["label"].startswith("Freight minimum")


def test_next_break_is_cheaper():
    option = sheet_option(*lane("Yellowtail Air Freight", "FRA-ORD"), 90, 0.4)
    assert option["total"] == 319.00 and option["billed_weight_kg"] == 100 and option["chargeable_weight_kg"] == 90


def test_volume_weight_dominates():
    helix = sheet_option(*lane("Helix Air Freight", "FRA-LAX"), 300, 2.5)
    wayzata = sheet_option(*lane("Wayzata Air Cargo", "FRA-LAX"), 300, 2.5)
    assert helix["chargeable_weight_kg"] == 417.5
    assert helix["total"] == 1607.38 and helix["transit_days"] == 1
    assert wayzata["total"] == 1160.66 and wayzata["transit_days"] == 4
    assert sum(line["amount"] for line in wayzata["breakdown"]) == wayzata["total"]


def test_cheapest_vs_fastest_on_the_same_lane():
    p = offline_pricer()
    cheapest = price(p, rfq("FRA", "LAX", 300, 2.5))
    fastest = price(p, rfq("FRA", "LAX", 300, 2.5, ask="fastest"))
    assert cheapest["chosen"]["carrier"] == "Wayzata Air Cargo" and cheapest["chosen"]["total"] == 1160.66
    assert fastest["chosen"]["carrier"] == "Helix Air Freight" and fastest["chosen"]["total"] == 1607.38
    assert [o["total"] for o in cheapest["options"]] == sorted(o["total"] for o in cheapest["options"])


def test_weights_from_pieces_per_piece():
    request = {"pieces": [{"count": 3, "length_cm": 120, "width_cm": 80, "height_cm": 100, "weight_kg": 140}]}
    assert weights(request) == (420, 2.88)  # 3 × 140 kg; 3 × 0.96 cbm → 480.96 kg volume weight


def test_expired_tariffs_are_not_used():
    assert price(offline_pricer(), rfq("FRA", "LAX", 300, 2.5, ready="2026-12-02"))["chosen"] is None


def test_past_or_mistyped_ready_date_prices_for_today():
    assert price(offline_pricer(), rfq("FRA", "LAX", 300, 2.5, ready="2025-11-23"))["chosen"]["total"] == 1160.66


def test_slow_portal_does_not_block_the_quote():
    class Slow(Portal):
        async def rate(self, *a, **kw):
            await asyncio.sleep(30)

    import pricing
    pricing.PORTAL_DEADLINE_S, old = 0.2, pricing.PORTAL_DEADLINE_S
    try:
        result = price(Pricer(TARIFFS, Zones(), Slow(api_key="k")), rfq("FRA", "LAX", 300, 2.5))
    finally:
        pricing.PORTAL_DEADLINE_S = old
    assert result["chosen"]["total"] == 1160.66 and "too slow" in result["why"]


def test_missing_weight_or_lane():
    p = offline_pricer()
    assert price(p, rfq("FRA", "LAX", 0, 0))["chosen"] is None
    assert price(p, rfq("FRA", "XXX", 100, 0))["chosen"] is None


def test_air_bids_compete_with_sheets():
    bid = {"source": "carrier_bid", "leg": "air", "carrier": "Ibisair Cargo", "rate_id": "B-1", "currency": "EUR",
           "total": 999.0, "transit_days": 3}
    result = price(offline_pricer(), rfq("FRA", "LAX", 300, 2.5), [bid])
    assert result["chosen"]["carrier"] == "Ibisair Cargo" and result["chosen"]["source"] == "carrier_bid"


def test_bids_only_lane_uses_the_balanced_choice():
    bids = [{"leg": "air", "carrier": "Cheap Slow", "currency": "EUR", "total": 1000.0, "transit_days": 9},
            {"leg": "air", "carrier": "Balanced", "currency": "EUR", "total": 1100.0, "transit_days": 3},
            {"leg": "air", "carrier": "Fast Dear", "currency": "EUR", "total": 2500.0, "transit_days": 2}]
    result = price(offline_pricer(), rfq("MUC", "KTM", 100, 0.2), bids)
    assert result["chosen"]["carrier"] == "Cheap Slow"  # the customer asked for cheapest
    import pricing
    pricing.BIDS_ONLY_CHOICE, old = "balanced", pricing.BIDS_ONLY_CHOICE
    try:
        result = price(offline_pricer(), rfq("MUC", "KTM", 100, 0.2), bids)
    finally:
        pricing.BIDS_ONLY_CHOICE = old
    assert result["chosen"]["carrier"] == "Balanced" and result["why"].startswith("balanced")


def test_door_to_port_adds_the_trucker_and_uses_the_zone_airport():
    trucks = [{"leg": "pickup", "carrier": "Isarwelle Spedition", "currency": "EUR", "total": 85.0, "transit_days": 1},
              {"leg": "pickup", "carrier": "Neckarstrom Kurier", "currency": "EUR", "total": 140.0, "transit_days": 1}]
    pickup = {"address": "Mainzer Landstr. 5, 60311 Frankfurt", "zone": None}
    result = price(offline_pricer(), rfq("XYZ", "LAX", 300, 2.5, pickup=pickup), trucks)
    chosen = result["chosen"]
    assert chosen["carrier"] == "Wayzata Air Cargo" and chosen["total"] == 1245.66  # 1160.66 air + 85.00 pickup
    assert chosen["pickup"]["carrier"] == "Isarwelle Spedition" and chosen["transit_days"] == 5
    assert chosen["breakdown"][-1] == {"label": "Pickup zone 60 (Frankfurt am Main) by Isarwelle Spedition",
                                       "amount": 85.0}
    assert "flies from FRA" in result["why"]


def test_door_to_port_without_trucker_bid_has_no_quote():
    pickup = {"address": "Hauptstr. 1, 60311 Frankfurt", "zone": None}
    result = price(offline_pricer(), rfq("FRA", "LAX", 300, 2.5, pickup=pickup))
    assert result["chosen"] is None and result["options"] and "no trucker bid" in result["why"]


def test_choose_rules():
    a = {"total": 100.0, "transit_days": 5}
    b = {"total": 100.0, "transit_days": 3}
    c = {"total": 90.0, "transit_days": None}
    assert choose([a, b, c], "cheapest") is c
    assert choose([a, b], "cheapest") is b  # same price: the faster one
    assert choose([a, b, c], "fastest") is b
    assert choose([], "fastest") is None


# --- portal (mocked 5U API) ---
def fake_portal(rates: dict, currency="EUR", fx=None) -> Portal:
    """rates: (airline, weight_kg) → total. Brackets 0/45/100/300/500/1000 for every airline."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params
        if request.url.path == "/v1/portal/ports":
            return httpx.Response(200, json={"lanes": [{"origin": "FRA", "destination": "LAX", "airlines": [
                {"code": "GN", "name": "Gannet Airways"}, {"code": "MD", "name": "Meridian Freightways"}]}]})
        if request.url.path == "/v1/portal/brackets":
            return httpx.Response(200, json={"airline": q["airline"], "breaks_kg": [0, 45, 100, 300, 500, 1000]})
        if request.url.path == "/v1/portal/rates":
            calls.append((q["airline"], float(q["weight_kg"])))
            weight = max(float(q["weight_kg"]), float(q["volume_cbm"]) * 167)
            total = rates.get((q["airline"], float(q["weight_kg"])))
            if total is None:
                return httpx.Response(503, json={"detail": "unavailable"})
            body = {"rate_id": f"R-{q['airline']}{int(weight):08d}", "airline": q["airline"] + " Air",
                    "airline_code": q["airline"], "origin": "FRA", "destination": "LAX", "weight_kg": q["weight_kg"],
                    "chargeable_weight_kg": f"{weight:.2f}", "total": f"{total:.2f}", "currency": currency,
                    "fx_eur_per_usd": fx, "transit_days": 2,
                    "valid_until": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    portal = Portal(base_url="https://portal.test", api_key="k", transport=httpx.MockTransport(handler))
    portal.calls = calls
    return portal


def test_portal_rates_and_next_break_check():
    # 90 kg: own bracket 400, the 100 kg break 350 (cheaper). 300 kg is > 1.5 × 90: never asked.
    portal = fake_portal({("GN", 90): 400.0, ("GN", 100): 350.0, ("MD", 90): 380.0, ("MD", 100): 390.0})
    pricer = Pricer(TARIFFS, Zones(), portal)
    result = price(pricer, rfq("FRA", "LAX", 90, 0.1))
    gannet = next(o for o in result["options"] if o.get("airline_code") == "GN")
    assert gannet["total"] == 350.0 and gannet["billed_weight_kg"] == 100 and gannet["rate_id"] == "R-GN00000100"
    assert gannet["chargeable_weight_kg"] == 90 and "billed at the 100 kg break" in gannet["breakdown"][0]["label"]
    meridian = next(o for o in result["options"] if o.get("airline_code") == "MD")
    assert meridian["total"] == 380.0  # the 100 kg break costs more: keep the own bracket
    assert sorted(portal.calls) == [("GN", 90), ("GN", 100), ("MD", 90), ("MD", 100)]

    price(pricer, rfq("FRA", "LAX", 90, 0.1))  # same request again: answered from the cache
    assert len(portal.calls) == 4


def test_prefetch_fills_the_cache():
    portal = fake_portal({("GN", 300): 1000.0, ("MD", 300): 900.0})
    pricer = Pricer(Tariffs(), Zones(), portal)
    asyncio.run(pricer.prefetch(rfq("FRA", "LAX", 300, 0.5)))
    assert len(portal.calls) == 2
    assert price(pricer, rfq("FRA", "LAX", 300, 0.5))["chosen"]["total"] == 900.0 and len(portal.calls) == 2


def test_optional_calls_respect_the_rate_limit_reserve():
    portal = fake_portal({("GN", 90): 400.0, ("GN", 100): 350.0, ("MD", 90): 380.0, ("MD", 100): 390.0})
    portal._budget = (int(__import__("time").time() // 60), 2)  # 2 calls left this minute
    price(Pricer(Tariffs(), Zones(), portal), rfq("FRA", "LAX", 90, 0.1))
    assert sorted(portal.calls) == [("GN", 90), ("MD", 90)]  # must-have lookups only


def test_portal_non_eur_is_converted():
    portal = fake_portal({("GN", 300): 1000.0, ("MD", 300): 5000.0}, currency="USD", fx="0.92")
    result = price(Pricer(Tariffs(), Zones(), portal), rfq("FRA", "LAX", 300, 0.5))
    assert result["chosen"]["total"] == 920.0 and result["chosen"]["currency"] == "EUR"
    assert "USD 1000.00 × 0.92" in result["chosen"]["breakdown"][0]["label"]
    assert portal.fx == {"USD": 0.92}


def test_door_to_port_takes_the_cheapest_trucker_even_for_a_fastest_request():
    # The trucker bids of live round 2 (Bad Homburg, zone 61 -> FRA): the fastest truck cost us 10.86 points.
    trucks = [{"leg": "pickup", "carrier": c, "currency": "EUR", "total": t, "transit_days": d} for c, t, d in (
        ("Hansekogge Trucking", 245.02, 0.9583), ("Westfalenroute", 266.03, 0.9583), ("Spessart Spedition", 299.03, 1.0417),
        ("Bodenseefracht", 119.01, 1.25), ("Nordlicht Haulage", 152.01, 1.25))]
    pickup = {"address": "61348 Bad Homburg", "zone": None}
    result = price(offline_pricer(), rfq("XYZ", "LAX", 300, 2.5, ask="fastest", pickup=pickup), trucks)
    assert result["chosen"]["pickup"]["carrier"] == "Bodenseefracht"


def test_booked_weight_is_the_full_shipment_weight():
    request = {"pieces": [{"count": 12, "weight_kg": 102.333333}], "volume_m3": 5.37}
    assert weights(request)[0] == 1228.0  # rounds 5 and 6 were booked at 1227.96 / 1548.96 and didn't count as booked


def test_round_9_trucker_is_ratio_balanced():
    # FRA-LOS, cheapest, door-to-port from Fulda: 5U's best used Domblick (361.24, 8 h), not Vogelsberg (194.64, 29 h)
    trucks = [{"leg": "pickup", "carrier": "Vogelsberg Haulage", "currency": "EUR", "total": 194.64, "transit_days": 29 / 24},
              {"leg": "pickup", "carrier": "Domblick Kurierdienst", "currency": "EUR", "total": 361.24, "transit_days": 8 / 24}]
    pickup = {"address": "Hauptstr. 1, 36037 Fulda", "zone": None}
    result = price(offline_pricer(), rfq("FRA", "LAX", 300, 2.5, pickup=pickup), trucks)
    assert result["chosen"]["pickup"]["carrier"] == "Domblick Kurierdienst"


def test_price_guard_warns_but_still_quotes():
    result = price(offline_pricer(), rfq("FRA", "LAX", 300, 2.5))
    assert result["chosen"] is not None
    # offline: the portal airlines on FRA-LAX (GN, MD) could not be priced, so the guard says so
    assert any("sheet/portal sources priced" in w for w in result["warnings"]) and "CHECK:" in result["why"]
    clean = price(Pricer(TARIFFS, Zones(), fake_portal({("GN", 300): 1500.0, ("MD", 300): 1600.0})), rfq("FRA", "LAX", 300, 2.5))
    assert clean["warnings"] == []


def test_a_hanging_lane_list_never_delays_the_price_check():
    class HangingLanes(Portal):
        async def airlines(self, *a, **kw):
            await asyncio.sleep(30)

    import time
    import pricing
    pricing.PORTAL_DEADLINE_S, old = 0.2, pricing.PORTAL_DEADLINE_S
    start = time.monotonic()
    try:
        result = price(Pricer(TARIFFS, Zones(), HangingLanes(api_key="k")), rfq("FRA", "LAX", 300, 2.5))
    finally:
        pricing.PORTAL_DEADLINE_S = old
    assert result["chosen"]["total"] == 1160.66 and time.monotonic() - start < 2  # deadline + 0.2 s guard, not 30 s


def test_an_airline_the_customer_ruled_out_is_never_chosen():
    """R42: 'Please do not offer Zephyr Steppe Cargo (ZS)' → rejected excluded_airline."""
    import asyncio
    pricer = Pricer(TARIFFS, Zones(), Portal(api_key=""))
    rfq = {"origin": "FRA", "destination": "ULN", "ask": "cheapest", "pickup": None, "ready_date": "2026-11-25",
           "pieces": [{"count": 1, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 500}],
           "volume_m3": 1.0}
    bids = [{"source": "carrier_bid", "leg": "air", "carrier": "Zephyr Steppe Cargo", "rate_id": "R-z", "currency": "EUR",
             "total": 2780.0, "transit_days": 5},
            {"source": "carrier_bid", "leg": "air", "carrier": "Lumen Air Cargo", "rate_id": "R-l", "currency": "EUR",
             "total": 3100.0, "transit_days": 4}]
    assert asyncio.run(pricer.price(rfq, bids))["chosen"]["carrier"] == "Zephyr Steppe Cargo"
    out = asyncio.run(pricer.price({**rfq, "excluded_airlines": ["Zephyr Steppe Cargo", "ZS"]}, bids))
    assert out["chosen"]["carrier"] == "Lumen Air Cargo" and "excluded by the customer" in out["why"]
def test_an_airline_the_customer_excluded_is_never_chosen():
    """Round 42: 'Please do not offer Zephyr Steppe Cargo (ZS)', we quoted it anyway → rejected excluded_airline."""
    base = price(offline_pricer(), rfq("FRA", "LAX", 300, 2.5))
    first = base["chosen"]["carrier"]
    other = price(offline_pricer(), {**rfq("FRA", "LAX", 300, 2.5), "excluded_airlines": [first]})
    assert other["chosen"] is None or other["chosen"]["carrier"] != first
    assert all(o["carrier"] != first for o in other["options"]) and "excluded by the customer" in other["why"]


def test_an_excluded_trucker_is_never_the_pickup_leg():
    """'Please don't use Isarwelle Spedition for the pickup': the next trucker, though it costs more."""
    trucks = [{"leg": "pickup", "carrier": "Isarwelle Spedition", "currency": "EUR", "total": 85.0, "transit_days": 1},
              {"leg": "pickup", "carrier": "Neckarstrom Kurier", "currency": "EUR", "total": 140.0, "transit_days": 1}]
    pickup = {"address": "Mainzer Landstr. 5, 60311 Frankfurt", "zone": None}
    request = {**rfq("XYZ", "LAX", 300, 2.5, pickup=pickup), "excluded_airlines": ["Isarwelle Spedition"]}
    chosen = price(offline_pricer(), request, trucks)["chosen"]
    assert chosen["pickup"]["carrier"] == "Neckarstrom Kurier"



def test_a_misread_tiny_trucker_bid_never_wins_the_pickup():
    """R68: Bodenseefracht EUR 45.00 for 1,494 kg (the waiting-time line) → quote rejected too_low."""
    from pricing import _sane_trucks
    trucks = [{"carrier": "Maintal", "total": 198.40, "transit_days": None},
              {"carrier": "Taunusfracht", "total": 284.22, "transit_days": None},
              {"carrier": "Domblick", "total": 367.98, "transit_days": None},
              {"carrier": "Bodenseefracht", "total": 45.00, "transit_days": 1.29},
              {"carrier": "Grautal", "total": 382.98, "transit_days": 0.29}]
    keep, odd = _sane_trucks(trucks, 1494.0, 0)
    assert [t["carrier"] for t in keep] == ["Maintal", "Taunusfracht", "Domblick", "Grautal"] and odd
    assert all(t["transit_days"] for t in keep)
