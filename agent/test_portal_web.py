"""PROTOTYPE portal_web (test environment only; 5U gave us the NopeCHA extension and allowed it there). No browser and
no live call here: the reader, the switches, and the hook into the RFQ path with a fake lookup."""
import time

import portal_web
import rfq_agent
from test_next_traps_15b import DOWN, _option, _run


def test_off_by_default_and_needs_its_settings(monkeypatch):
    monkeypatch.setattr(portal_web, "ON", False)
    assert portal_web.ready() == "PORTAL_WEB is off" and portal_web.rates("FRA", "LAX", ["Xenon"], 300) == []
    monkeypatch.setattr(portal_web, "ON", True)
    monkeypatch.setattr(portal_web, "URL", "")
    monkeypatch.setattr(portal_web, "KEY", "")
    assert "PORTAL_WEB_URL" in portal_web.ready() and "NOPECHA_KEY" in portal_web.ready()


def test_reads_price_transit_and_rate_id_from_the_page_text():
    assert portal_web.read_rate("Xenon Cargo Airlines\nAll-in EUR 5,890.50\nTransit 3 days\nRate R-AbCdEf1234") == \
        {"total": 5890.5, "currency": "EUR", "transit_days": 3.0, "rate_id": "R-AbCdEf1234"}
    assert portal_web.read_rate("Total 1.234,50 € · 2 d")["total"] == 1234.5
    assert portal_web.read_rate("Please solve the challenge") is None


def test_portal_down_prices_the_silent_airlines_from_the_web_page(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_web, "ready", lambda: None)
    asked = []
    monkeypatch.setattr(portal_web, "rates", lambda o, d, airlines, kg, m3: (asked.append(airlines), [
        {"source": "portal_web", "leg": "air", "carrier": "Gannet Airways", "total": 1460.0, "currency": "EUR",
         "transit_days": 1.0, "rate_id": None}])[1])
    priced = {"options": [_option("Gannet Airways", 1460.0)], "chosen": _option("Gannet Airways", 1460.0), "why": "ok"}
    box, api, desk = _run(tmp_path, monkeypatch, [{"options": [], "chosen": None, "why": DOWN}, priced], None)
    assert asked and "Gannet Airways" in asked[0]
    assert box.sent[-1]["thread_id"] == "t1" and "1,460.00" in box.sent[-1]["body"]
    assert desk == []  # priced from the page: the desk isn't needed


def test_default_off_never_changes_the_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_web, "ON", False)
    called = []
    monkeypatch.setattr(portal_web, "rates", lambda *a: called.append(a) or [])
    sheet = {"options": [_option("Wayzata", 1100.0, "sheet")], "chosen": _option("Wayzata", 1100.0, "sheet"),
             "why": "cheapest: Wayzata (sheet); portal: rates GN: 503 unavailable"}
    box, api, desk = _run(tmp_path, monkeypatch, [sheet], None)
    assert called == [] and len(desk) == 1


def test_an_airline_the_backends_web_form_priced_is_not_looked_up_again(monkeypatch):
    monkeypatch.setattr(portal_web, "ready", lambda: None)
    asked = []
    monkeypatch.setattr(portal_web, "rates", lambda o, d, airlines, kg, m3: asked.append(airlines) or [])
    form = {**_option("Gannet Airways", 1460.0, "portal"), "portal_form": True}
    result = {"options": [form], "chosen": form, "why": DOWN}
    rfq = {"origin": "FRA", "destination": "LAX", "pieces": [{"count": 1, "weight_kg": 300}]}
    bids, out = rfq_agent._portal_web_round(1, rfq, [], result, [{"name": "Gannet Airways", "kind": "airline"}], None)
    assert asked == [] and out is result
