"""R179 (session 186, too_high): weidner CGN → ORD, cheapest, ready 27 Nov, "must be at ORD by 2026-11-29 … price is
what will decide". The gate kept Aurelia (2-day flight: 29 Nov, as 5U counts it) over Xenon (3-day flight: 30 Nov), but
the mail said "around 30 Nov", and the later price match offered Xenon. The arrive-by date now rides on the request."""
from datetime import date

import pytest

import gate
import price_match
import quote_style
import rfq_agent
from test_price_match import Api, amounts, reply

PICKUP = {"carrier": "Westfalenroute", "rate_id": None, "total": 145.16, "transit_days": 0.46}
AURELIA = {"source": "portal", "carrier": "Aurelia Air Cargo", "rate_id": "R-AU1", "currency": "EUR",
           "total": 1074.69, "transit_days": 2.46, "pickup": PICKUP}
XENON = {"source": "portal", "carrier": "Xenon Air Freight", "rate_id": "R-XE1", "currency": "EUR",
         "total": 927.20, "transit_days": 3.46, "pickup": PICKUP}
RFQ = {"origin": "CGN", "destination": "ORD", "ask": "cheapest", "ready_date": "2026-11-27", "language": "en",
       "pickup": {"address": "51465 Bergisch Gladbach, Germany", "zone": None}, "arrive_by": "2026-11-29",
       "pieces": [{"count": 2, "weight_kg": 77.8}], "contact_name": "Klaus Weidner"}
TODAY = date(2026, 11, 22)


def test_the_mail_states_the_gates_arrival():
    _, departs, arrives = quote_style._dates(RFQ, AURELIA, TODAY)
    assert arrives == date(2026, 11, 29) == gate._arrives(AURELIA, date(2026, 11, 27))
    assert departs == date(2026, 11, 27)  # 2-day flight: leaves on the ready day, lands on the 29th


def test_without_a_deadline_the_mail_is_as_before():
    rfq = {k: v for k, v in RFQ.items() if k != "arrive_by"}
    _, departs, arrives = quote_style._dates(rfq, AURELIA, TODAY)
    assert (departs, arrives) == (date(2026, 11, 28), date(2026, 11, 30))  # #95 wording


def test_arrival_as_gate_off(monkeypatch):
    monkeypatch.setattr(quote_style, "ARRIVAL_AS_GATE", False)
    assert quote_style._dates(RFQ, AURELIA, TODAY)[2] == date(2026, 11, 30)


def test_the_cheaper_truckers_extra_hours_never_move_the_arrival():
    elbkante = {**AURELIA, "total": 1020.54, "transit_days": 3.21,
                "pickup": {**PICKUP, "carrier": "Elbkante Logistik", "total": 91.01, "transit_days": 1.21}}
    assert gate.in_time(elbkante, RFQ) and quote_style._dates(RFQ, elbkante, TODAY)[2] == date(2026, 11, 29)


def test_in_time():
    assert gate.in_time(AURELIA, RFQ) and not gate.in_time(XENON, RFQ)
    assert gate.in_time(XENON, {**RFQ, "arrive_by": None}) and gate.in_time(XENON, {**RFQ, "arrive_by": "2026-11-30"})


def test_r179_the_price_match_never_offers_the_late_xenon(tmp_path):
    session = {"id": 186, "customer": "weidner-spielwaren@hackloop.mail", "thread_id": 7, "stage": "quoted",
               "llm_cost_usd": 0.0001, "rfq": RFQ, "quote": AURELIA, "bids": []}
    api, box = reply("Another forwarder quoted 7% less, can you match?", [XENON, AURELIA], tmp_path, session)
    assert amounts(box.sent[0]["body"]) == ["EUR 1,074.69"] and api.state["quote"] == AURELIA


@pytest.mark.parametrize("body, by", [
    ("1 crate, 300 kg, FRA to LAX, ready 25 Nov. Must be at LAX by 2026-11-29; price is what will decide.", "2026-11-29"),
    ("1 crate, 300 kg, FRA to LAX, ready 25 Nov. Best price please.", None),
])
def test_the_request_carries_its_arrive_by_date(tmp_path, monkeypatch, body, by):
    import extract as extract_mod
    from bids import BidBoard
    from inbox import FixtureMailbox
    from test_next_traps_15b import CARRIERS, MAIL, RAW, Api as RfqApi
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    priced = []
    monkeypatch.setattr(rfq_agent, "_price_and_quote", lambda session_id, mail, rfq, *a, **k: priced.append(rfq))
    rfq_agent.handle_rfq({**MAIL, "body": body, "received_at": "2026-11-22T08:40:00+00:00"}, FixtureMailbox(tmp_path),
                         RfqApi([{"options": [], "chosen": None, "why": ""}]), BidBoard(), CARRIERS, 0.2)
    assert [r.get("arrive_by") for r in priced] == [by]


@pytest.mark.parametrize("flag", [True, False])
def test_same_service_off_keeps_the_old_price_match(tmp_path, monkeypatch, flag):
    monkeypatch.setattr(price_match, "SAME_SERVICE", flag)
    session = {"id": 186, "customer": "weidner-spielwaren@hackloop.mail", "thread_id": 7, "stage": "quoted",
               "llm_cost_usd": 0.0001, "rfq": RFQ, "quote": AURELIA, "bids": []}
    api, box = reply("Can you match 7% less?", [XENON, AURELIA], tmp_path, session)
    assert amounts(box.sent[0]["body"]) == (["EUR 1,074.69"] if flag else ["EUR 927.20"])
