"""PORTAL_MEMORY (R93/R94: the rate API answered 503 for a whole round): the portal's earlier answers for the same lane
and airline price the request, per kg of the nearest remembered weight, while its rate calls fail."""

import asyncio

import portal_memory
from crm import Crm
from portal_memory import PortalMemory
from pricing import Pricer
from tariffs import Tariffs, Zones
from test_pricing import fake_portal, rfq


def _seed(crm: Crm, request: dict, options: list[dict], text: str = "Priced") -> int:
    sid = crm.create_session("anna@customer.test", f"t-{len(options)}-{text}", "2026-11-22T00:00:00+00:00")
    crm.update(sid, {"rfq": request})
    crm.add_event({"session_id": sid, "kind": "priced", "text": text, "data": {"options": options}})
    return sid


def _portal(code, total, billed, **extra):
    return {"source": "portal", "carrier": f"{code} Air", "airline_code": code, "rate_id": f"R-{code}1", "total": total,
            "total_eur": total, "transit_days": 2, "chargeable_weight_kg": billed, "billed_weight_kg": billed, **extra}


def _pricer(crm, rates):
    pricer = Pricer(Tariffs(), Zones(), fake_portal(rates))  # no sheets: only portal options can price
    pricer.memory = PortalMemory(crm, lambda r: pricer.lane(r, [])[:2])
    return pricer


def test_a_failed_portal_prices_from_its_remembered_answer_per_kg():
    crm = Crm(":memory:")
    sid = _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 1200.0, 300), _portal("MD", 1350.0, 300)])
    pricer = _pricer(crm, {})  # every rate call: 503
    result = asyncio.run(pricer.price(rfq("FRA", "LAX", 330, 0.5), []))
    gn = next(o for o in result["options"] if o["airline_code"] == "GN")
    assert gn["source"] == "portal" and gn["remembered"] and gn["rate_id"] is None
    assert gn["total"] == 1320.0 and gn["chargeable_weight_kg"] == 330  # EUR 4.00/kg × 330 kg
    assert f"session #{sid}" in gn["breakdown"][0]["label"]
    assert result["chosen"]["airline_code"] == "GN" and result["chosen"]["total"] == 1320.0
    assert "portal: rates" in result["why"] and "(lane airlines: GN, MD)" in result["why"] and "earlier answers used for GN Air EUR 1,320.00" in result["why"]


def test_pickup_and_insurance_are_taken_out_of_the_remembered_air_rate():
    crm = Crm(":memory:")
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 1500.0, 300, pickup={"total": 200.0},
                                                     insurance={"total": 100.0})])
    result = asyncio.run(_pricer(crm, {}).price(rfq("FRA", "LAX", 300, 0.5), []))
    assert result["chosen"]["total"] == 1200.0


def test_a_live_answer_wins_and_only_failed_airlines_are_remembered():
    crm = Crm(":memory:")
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 1200.0, 300), _portal("MD", 1350.0, 300)])
    result = asyncio.run(_pricer(crm, {("GN", 300): 1100.0}).price(rfq("FRA", "LAX", 300, 0.5), []))
    gn = [o for o in result["options"] if o["airline_code"] == "GN"]
    md = [o for o in result["options"] if o["airline_code"] == "MD"]
    assert len(gn) == 1 and not gn[0].get("remembered") and gn[0]["total"] == 1100.0
    assert len(md) == 1 and md[0]["remembered"] and md[0]["total"] == 1350.0


def test_the_nearest_weight_within_a_factor_two_and_nothing_further():
    crm = Crm(":memory:")
    _seed(crm, rfq("FRA", "LAX", 100, 0.2), [_portal("GN", 500.0, 100)])  # EUR 5.00/kg
    _seed(crm, rfq("FRA", "LAX", 1000, 2.0), [_portal("GN", 3000.0, 1000)], "Priced again")  # EUR 3.00/kg
    pricer = _pricer(crm, {})
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 150, 0.2), []))["chosen"]["total"] == 750.0
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 800, 1.0), []))["chosen"]["total"] == 2400.0
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 3000, 5.0), []))["chosen"] is None  # ×3 away: another bracket


def test_other_lanes_lots_remembered_options_and_the_switch_are_never_used(monkeypatch):
    crm = Crm(":memory:")
    _seed(crm, rfq("MUC", "LAX", 300, 0.5), [_portal("GN", 900.0, 300)])
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 600.0, 300)], "Shipment to LAX (lot 2)")
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 700.0, 300, remembered=True)], "Priced remembered")
    pricer = _pricer(crm, {})
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 300, 0.5), []))["chosen"] is None
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 1200.0, 300)], "Priced later")
    pricer.memory._built = 0  # rebuild now
    monkeypatch.setattr(portal_memory, "ON", False)
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 300, 0.5), []))["chosen"] is None
    monkeypatch.setattr(portal_memory, "ON", True)
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 300, 0.5), []))["chosen"]["total"] == 1200.0


def test_the_newest_answer_wins_at_the_same_weight():
    crm = Crm(":memory:")
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 1200.0, 300)], "Priced old")
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 1260.0, 300)], "Priced new")
    assert asyncio.run(_pricer(crm, {}).price(rfq("FRA", "LAX", 300, 0.5), []))["chosen"]["total"] == 1260.0


def test_a_portal_without_failures_never_uses_the_memory():
    crm = Crm(":memory:")
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 1200.0, 300)])
    pricer = Pricer(Tariffs(), Zones(), fake_portal({}))
    pricer.portal.api_key = ""  # no key: no rate calls at all, nothing failed
    pricer.memory = PortalMemory(crm, lambda r: pricer.lane(r, [])[:2])
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 300, 0.5), []))["chosen"] is None


def test_the_app_gives_its_pricer_the_crm_memory():
    from app import create_app
    from test_app import FakeMailbox

    crm, pricer = Crm(":memory:"), Pricer(Tariffs(), Zones(), fake_portal({}))
    create_app(crm, FakeMailbox(), pricer)
    assert isinstance(pricer.memory, PortalMemory) and pricer.memory.crm is crm


def test_the_same_bracket_wins_over_a_closer_weight_in_another_bracket():
    # breaks 0/45/100/300/500/1000: 290 kg is in the 100 bracket. 300 kg (closer) is the 300 bracket's cheaper rate.
    crm = Crm(":memory:")
    _seed(crm, rfq("FRA", "LAX", 200, 0.3), [_portal("GN", 1000.0, 200)], "Priced 200")  # EUR 5.00/kg, 100 bracket
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 1200.0, 300)], "Priced 300")  # EUR 4.00/kg, 300 bracket
    chosen = asyncio.run(_pricer(crm, {}).price(rfq("FRA", "LAX", 290, 0.3), []))["chosen"]
    assert chosen["total"] == 1450.0 and chosen["remembered"] == "bracket"
    chosen = asyncio.run(_pricer(crm, {}).price(rfq("FRA", "LAX", 600, 1.0), []))["chosen"]  # 500 bracket: none seen
    assert chosen["total"] == 2400.0 and chosen["remembered"] == "nearest" and "nearest bracket" in \
        chosen["breakdown"][0]["label"]


# --- POST /api/sessions/{id}/portal-rate: a portal web-form result pasted by a person (portal_paste.py) ---
def test_a_pasted_portal_result_becomes_a_manual_portal_bid_once():
    from fastapi.testclient import TestClient

    from app import create_app
    from test_app import FakeMailbox

    crm = Crm(":memory:")
    client = TestClient(create_app(crm, FakeMailbox(), Pricer(Tariffs(), Zones(), fake_portal({}))))
    sid = crm.create_session("anna@customer.test", "t1")
    text = "Your rate\nGannet Airways · FRA → LAX\nRate ID R-GN7731A\nTransit 2 days\nTotal EUR 1,284.50\nValid 10 min"
    bid = client.post(f"/api/sessions/{sid}/portal-rate", json={"airline": "GN", "text": text}).json()
    assert bid == {"source": "carrier_bid", "leg": "air", "carrier": "Gannet Airways", "currency": "EUR",
                   "total": 1284.5, "transit_days": 2, "rate_id": "R-GN7731A", "manual_portal": True}
    client.post(f"/api/sessions/{sid}/portal-rate", json={"airline": "GN", "text": text})
    assert crm.session(sid)["bids"] == [bid]
    assert client.post(f"/api/sessions/{sid}/portal-rate", json={"text": "nothing here"}).status_code == 422


def test_the_paste_parser_reads_other_layouts():
    import portal_paste

    assert portal_paste.parse("<b>Xenon Cargo Airlines</b> 3 days <span>€ 912,40</span>")["total"] == 912.40
    usd = portal_paste.parse("USD 1,050.00 all-in, 4 d", "TM")
    assert usd["carrier"] == "Tamarind Airways" and usd["currency"] == "USD" and usd["transit_days"] == 4
    assert portal_paste.parse("Price: 1.234,50 EUR", "UV")["total"] == 1234.50
    assert portal_paste.parse("Total weight 300 kg, volume 1.1 cbm. Total EUR 980.00, 2 days", "GN")["total"] == 980.0


def test_the_form_lists_the_likely_winner_first():
    crm = Crm(":memory:")
    _seed(crm, rfq("FRA", "LAX", 300, 0.5), [_portal("GN", 1200.0, 300, transit_days=3),
                                             _portal("MD", 1350.0, 300, transit_days=1)])
    pricer = _pricer(crm, {})
    assert "(lane airlines: GN, MD)" in asyncio.run(pricer.price(rfq("FRA", "LAX", 300, 0.5), []))["why"]
    assert "(lane airlines: MD, GN)" in asyncio.run(pricer.price(rfq("FRA", "LAX", 300, 0.5, "fastest"), []))["why"]
