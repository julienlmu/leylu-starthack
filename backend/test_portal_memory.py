"""PORTAL_MEMORY (R93/R94: the rate API answered 503 for a whole round): the portal's earlier answers for the same lane
and airline price the request, per kg in the same weight bracket (never another bracket), while its rate calls fail."""

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
    assert "portal: rates" in result["why"] and "REMEMBERED portal rates" in result["why"] and "GN Air EUR 1,320.00 (2 d)" in result["why"]


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


def test_only_the_same_bracket_never_another_brackets_rate():
    # breaks 0/45/100/300/500/1000
    crm = Crm(":memory:")
    _seed(crm, rfq("FRA", "LAX", 100, 0.2), [_portal("GN", 500.0, 100)])  # EUR 5.00/kg, 100 bracket
    _seed(crm, rfq("FRA", "LAX", 1000, 2.0), [_portal("GN", 3000.0, 1000)], "Priced again")  # EUR 3.00/kg, 1000 bracket
    pricer = _pricer(crm, {})
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 150, 0.2), []))["chosen"]["total"] == 750.0
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 800, 1.0), []))["chosen"] is None  # 500 bracket: none seen
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 3000, 5.0), []))["chosen"]["total"] == 9000.0  # 1000+ bracket


def test_the_lowest_bracket_and_unknown_breaks_take_only_the_same_weight():
    crm = Crm(":memory:")
    _seed(crm, rfq("FRA", "LAX", 30, 0.05), [_portal("GN", 150.0, 30)])  # under 45 kg: the minimum may bind
    pricer = _pricer(crm, {})
    assert asyncio.run(pricer.price(rfq("FRA", "LAX", 40, 0.05), []))["chosen"] is None
    chosen = asyncio.run(pricer.price(rfq("FRA", "LAX", 30, 0.05), []))["chosen"]
    assert chosen["total"] == 150.0 and chosen["remembered"] == "weight"
    _seed(crm, rfq("FRA", "LAX", 330, 0.5), [_portal("GN", 1320.0, 330)])
    pricer.memory._built = 0
    options = pricer.memory.options("FRA", "LAX", [{"code": "GN", "name": "GN Air"}], 350)  # breaks unknown
    assert options == []
    assert pricer.memory.options("FRA", "LAX", [{"code": "GN", "name": "GN Air"}], 330)[0]["total"] == 1320.0


def test_answers_older_than_the_max_age_are_never_used():
    crm = Crm(":memory:")
    sid = crm.create_session("anna@customer.test", "t-old", "2026-11-20T00:00:00+00:00")
    crm.update(sid, {"rfq": rfq("FRA", "LAX", 300, 0.5)})
    crm.add_event({"session_id": sid, "kind": "priced", "text": "Priced", "at": "2020-01-01T00:00:00+00:00",
                   "data": {"options": [_portal("GN", 1200.0, 300)]}})
    assert asyncio.run(_pricer(crm, {}).price(rfq("FRA", "LAX", 300, 0.5), []))["chosen"] is None


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
    assert "same bracket" in chosen["breakdown"][0]["label"]


# --- POST /api/sessions/{id}/portal-rate: a portal web-form result pasted by a person (portal_paste.py) ---
def _paste_client(monkeypatch, secret="s3cret"):
    from fastapi.testclient import TestClient

    import app
    from test_app import FakeMailbox

    monkeypatch.setattr(app, "PORTAL_PASTE_SECRET", secret)
    crm = Crm(":memory:")
    client = TestClient(app.create_app(crm, FakeMailbox(), Pricer(Tariffs(), Zones(), fake_portal({}))))
    sid = crm.create_session("anna@customer.test", "t1")
    crm.update(sid, {"rfq": rfq("FRA", "LAX", 300, 0.5)})
    return client, crm, sid


PASTE = "Your rate\nGannet Airways · FRA → LAX\nRate ID R-GN7731A\nTransit 2 days\nTotal EUR 1,284.50\nValid 10 min"


def test_a_pasted_portal_result_becomes_a_manual_portal_bid_once(monkeypatch):
    client, crm, sid = _paste_client(monkeypatch)
    paste = {"airline": "GN", "origin": "FRA", "destination": "LAX", "text": PASTE}
    ok = {"X-Paste-Secret": "s3cret"}
    bid = client.post(f"/api/sessions/{sid}/portal-rate", json=paste, headers=ok).json()
    assert bid == {"source": "carrier_bid", "leg": "air", "carrier": "Gannet Airways", "airline_code": "GN", "currency": "EUR",
                   "total": 1284.5, "transit_days": 2, "rate_id": "R-GN7731A", "manual_portal": True}
    client.post(f"/api/sessions/{sid}/portal-rate", json=paste, headers=ok)
    assert crm.session(sid)["bids"] == [bid]
    assert sum("Portal rate pasted" in e["text"] for e in crm.events(sid)) == 2  # every paste is logged
    # the agent writing its own bids never drops the person's rate
    client.patch(f"/api/sessions/{sid}", json={"bids": [{"carrier": "Air X", "total": 900.0}]})
    assert bid in crm.session(sid)["bids"]


def test_the_paste_endpoint_needs_the_secret_and_checks_every_field(monkeypatch):
    client, crm, sid = _paste_client(monkeypatch)
    paste = {"airline": "GN", "origin": "FRA", "destination": "LAX", "text": PASTE}
    url = f"/api/sessions/{sid}/portal-rate"
    assert client.post(url, json=paste).status_code == 403
    assert client.post(url, json=paste, headers={"X-Paste-Secret": "wrong"}).status_code == 403
    ok = {"X-Paste-Secret": "s3cret"}
    for bad in ({"origin": "MUC"}, {"airline": "ZZ"}, {"airline": "Evil Air"}, {"text": "nothing here"},
                {"text": PASTE.replace("1,284.50", "9.00")}, {"text": PASTE.replace("1,284.50", "99,999.00")},
                {"text": PASTE.replace("2 days", "400 days")}, {"text": PASTE + "x" * 6000}):
        assert client.post(url, json={**paste, **bad}, headers=ok).status_code == 422, bad
    assert not crm.session(sid)["bids"]
    assert sum("paste refused" in e["text"] for e in crm.events(sid)) == 8
    crm.update(sid, {"quote": {"total": 1000.0}})
    assert client.post(url, json=paste, headers=ok).status_code == 422  # quoted: nothing to change any more
    client, _, sid = _paste_client(monkeypatch, secret="")  # no secret configured: the endpoint is off
    assert client.post(f"/api/sessions/{sid}/portal-rate", json=paste, headers={"X-Paste-Secret": ""}).status_code == 403


def test_a_live_portal_answer_wins_over_a_pasted_or_web_page_rate():
    pasted = {"source": "carrier_bid", "leg": "air", "carrier": "Gannet Airways", "airline_code": "GN",
              "currency": "EUR", "total": 900.0, "manual_portal": True}
    web = {"leg": "air", "carrier": "GN Air", "currency": "EUR", "total": 950.0, "portal_web": True}
    md = {**pasted, "carrier": "Meridian Freightways", "airline_code": "MD", "total": 1000.0}
    pricer = Pricer(Tariffs(), Zones(), fake_portal({("GN", 300.0): 1200.0}))  # GN answers live, MD 503
    result = asyncio.run(pricer.price(rfq("FRA", "LAX", 300, 0.5), [pasted, web, md]))
    assert result["chosen"]["carrier"] == "Meridian Freightways"  # MD's pasted rate: nothing live for MD
    assert [o["total"] for o in result["options"] if "GN" in o["carrier"] or "Gannet" in o["carrier"]] == [1200.0]
    assert "by-hand rates for Gannet Airways, GN Air dropped" in result["why"]


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


# ---- PORTAL_SURGE (R122 too_low): the portal raises every airline at once for a while, by x1.15 / x1.30


def _ago(hours: float) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


def _seed_at(crm: Crm, at: str, request: dict, options: list[dict]) -> int:
    sid = _seed(crm, request, options, f"Priced {at}")
    crm.db.execute("UPDATE events SET at = ? WHERE session_id = ?", (at, sid))
    crm.db.commit()
    return sid


def _night(crm):
    """The night of 21/22 Nov in small: FRA-LAX unsurged at 15:50, x1.15 at 20:11 (with another lane at x1.15 too)."""
    _seed_at(crm, _ago(11.6), rfq("FRA", "LAX", 1000, 0.5), [_portal("GN", 3440.0, 1000),
                                                                             _portal("MD", 2480.0, 1000)])
    _seed_at(crm, _ago(7.3), rfq("FRA", "LAX", 1000, 0.5), [_portal("GN", 3956.0, 1000),
                                                                             _portal("MD", 2852.0, 1000)])
    _seed_at(crm, _ago(7.5), rfq("MUC", "BKK", 1000, 0.5), [_portal("NV", 2920.0, 1000)])
    _seed_at(crm, _ago(7.4), rfq("MUC", "BKK", 1000, 0.5), [_portal("NV", 3358.0, 1000),
                                                                             _portal("PL", 3151.0, 1000)])
    _seed_at(crm, _ago(9.9), rfq("MUC", "BKK", 1000, 0.5), [_portal("PL", 2740.0, 1000)])


def test_a_surge_window_is_found_and_each_answer_gets_its_base():
    crm = Crm(":memory:")
    _night(crm)
    memory = PortalMemory(crm, lambda r: (r["origin"], r["destination"]))
    gn = sorted(r["per_kg"] for r in memory.rates("FRA", "LAX") if r["code"] == "GN")
    assert gn == [3.44, 3.956]
    assert all(abs(r["base"] - 3.44) < 0.01 for r in memory.rates("FRA", "LAX") if r["code"] == "GN")
    assert [f for _, f in memory._timeline if f != 1.0] == [1.15, 1.15]


def test_a_remembered_surged_answer_goes_back_to_its_base_when_no_surge_is_known():
    crm = Crm(":memory:")
    _night(crm)
    result = asyncio.run(_pricer(crm, {}).price(rfq("FRA", "LAX", 1100, 0.5), []))
    gn = next(o for o in result["options"] if o["airline_code"] == "GN")
    assert gn["total"] == round(3956.0 / 1000 / 1.15 * 1100, 2)  # the newest answer (20:11) brought back to its base
    assert "surge x1.15 then, x1.00 now" in gn["breakdown"][0]["label"]


def test_a_rate_a_person_pasted_sets_the_surge_for_the_other_remembered_airlines():
    crm = Crm(":memory:")
    _night(crm)
    pasted = {"carrier": "GN Air", "airline_code": "GN", "total": round(3.44 * 1.30 * 1100, 2), "currency": "EUR",
              "manual_portal": True, "leg": "air", "transit_days": 2}
    result = asyncio.run(_pricer(crm, {}).price(rfq("FRA", "LAX", 1100, 0.5), [pasted]))
    md = next(o for o in result["options"] if o.get("airline_code") == "MD")
    assert md["remembered"] and md["total"] == round(2.48 * 1.30 * 1100, 2)
    assert "x1.30 now (live GN Air rate now vs its base)" in md["breakdown"][0]["label"]


def test_one_lane_alone_never_makes_a_surge():
    """STR-MEL: 1,615 kg and 2,000 kg answers 15 % apart for both airlines are two brackets, not a surge."""
    crm = Crm(":memory:")
    _seed_at(crm, _ago(8.8), rfq("FRA", "LAX", 1615, 0.5), [_portal("GN", 4.64 * 1615, 1615),
                                                                             _portal("MD", 3.46 * 1615, 1615)])
    _seed_at(crm, _ago(4.2), rfq("FRA", "LAX", 2000, 0.5), [_portal("GN", 4.02 * 2000, 2000),
                                                                             _portal("MD", 3.03 * 2000, 2000)])
    memory = PortalMemory(crm, lambda r: (r["origin"], r["destination"]))
    assert all(r["base"] == r["per_kg"] for r in memory.rates("FRA", "LAX"))
    assert all(f == 1.0 for _, f in memory._timeline)


def test_surge_off_keeps_the_remembered_rate(monkeypatch):
    monkeypatch.setattr(portal_memory, "SURGE", False)
    crm = Crm(":memory:")
    _night(crm)
    result = asyncio.run(_pricer(crm, {}).price(rfq("FRA", "LAX", 1100, 0.5), []))
    gn = next(o for o in result["options"] if o["airline_code"] == "GN")
    assert gn["total"] == round(3.956 * 1100, 2)
