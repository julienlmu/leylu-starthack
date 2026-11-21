import re
import threading
import time

import extract as extract_mod
import rfq_agent
from bids import BidBoard
from extract import to_rfq
from inbox import FixtureMailbox

RAW = {
    "origin": "MUC", "destination": "JFK", "ask": None, "pickup_address": "Industriestr. 12, 85748 Garching",
    "ready_date": "2026-11-23",
    "pieces": [{"count": 2, "length": 48, "width": 40, "height": 40, "weight": 440, "weight_is_total": True}],
    "dim_unit": "in", "weight_unit": "lb", "volume_m3": None, "commodity": "machine parts",
    "dangerous_goods": False, "customer_reference": "PO-4711", "language": "de",
}
OPTION = {"source": "sheet", "carrier": "SkyAir", "rate_id": None, "currency": "EUR", "total": 1856.0,
          "transit_days": 2, "valid_until": "2026-11-28", "chargeable_weight_kg": 480, "breakdown": []}
MAIL = {"id": "m1", "thread_id": "t1", "from": "buyer@customer.example", "subject": "RFQ MUC-JFK", "body": "…"}
CARRIERS = [{"name": "SkyAir", "email": "bids@skyair.example", "kind": "airline", "serves": ["JFK"]},
            {"name": "CloudCargo", "email": "rates@cloud.example", "kind": "airline", "serves": ["*"]},
            {"name": "Huber Transporte", "email": "dispo@huber.example", "kind": "trucker", "serves": ["85"]}]


class FakeApi:
    def __init__(self, price_result):
        self.price_result, self.updates, self.events, self.bids = price_result, [], [], None
        self.data, self.received_at = {}, None

    def create_session(self, customer, thread_id, received_at=None):
        self.received_at = received_at
        return 1

    def session(self, session_id):
        return {"paused": False}

    def update(self, session_id, **fields):
        self.updates.append(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append(kind)
        self.data[kind] = data

    def price(self, rfq, bids=None):
        self.bids = bids
        return self.price_result


def test_to_rfq_converts_units_and_total_weight():
    rfq, missing = to_rfq(RAW)
    assert rfq["pieces"] == [{"count": 2, "length_cm": 121.9, "width_cm": 101.6, "height_cm": 101.6, "weight_kg": 99.79}]
    assert rfq["ask"] == "cheapest"
    assert rfq["pickup"] == {"address": "Industriestr. 12, 85748 Garching", "zone": None}
    assert missing == []


def test_door_to_port_origin_comes_from_the_pickup_zone():
    raw = {**RAW, "origin": None, "pickup_address": "51447 Bergisch Gladbach, Germany"}
    rfq, missing = to_rfq(raw)
    assert rfq["origin"] == "CGN" and "origin" not in missing
    raw = {**RAW, "origin": "MUC", "pickup_address": "Hauptstr. 1, 60311 Frankfurt"}
    assert to_rfq(raw)[0]["origin"] == "FRA"  # the pickup decides the airport


def test_to_rfq_lists_what_is_missing():
    raw = {**RAW, "origin": None, "pickup_address": None, "pieces": [{"count": 1, "length": None, "width": None, "height": None,
                                               "weight": None, "weight_is_total": False}]}
    assert to_rfq(raw)[1] == ["origin", "weight", "dimensions or volume"]


def test_handle_rfq_quotes_one_total_in_the_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION, "why": "cheapest"})
    rfq_agent.handle_rfq(MAIL, box, api)
    [sent] = box.sent
    assert sent["thread_id"] == "t1"
    assert re.findall(r"\d[\d,]*\.\d{2}", sent["body"]) == ["1,856.00"]
    assert "EUR 1,856.00" in sent["body"]
    assert api.events == ["mail_in", "routed", "extracted", "priced", "quote_sent"]
    assert api.updates[-1]["stage"] == "quoted"


def test_mail_events_carry_the_mails_and_the_session_gets_the_arrival_time(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION, "why": "cheapest"})
    mail = {**MAIL, "to": "leylu@hackloop.mail", "received_at": "2026-11-21T15:00:00+00:00"}
    rfq_agent.handle_rfq(mail, box, api)
    assert api.received_at == "2026-11-21T15:00:00+00:00"  # the UI's response time counts from here
    assert api.data["mail_in"] == {"from": "buyer@customer.example", "to": "leylu@hackloop.mail",
                                   "subject": "RFQ MUC-JFK", "body": "…"}
    quote = api.data["quote_sent"]
    assert (quote["from"], quote["to"], quote["subject"]) == ("leylu@hackloop.mail", "buyer@customer.example",
                                                              "Re: RFQ MUC-JFK")
    assert quote["body"] == box.sent[-1]["body"] and quote["option"] == OPTION


def test_handle_rfq_hands_over_without_mailing(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [], "chosen": None, "why": ""})
    rfq_agent.handle_rfq(MAIL, box, api)
    assert box.sent == []
    assert api.events[-1] == "needs_human"


def test_handle_rfq_asks_carriers_and_prices_with_their_bids(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))  # RAW wants pickup → trucker asked too
    box, api, board = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION}), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(MAIL, box, api, board, CARRIERS, 5))
    worker.start()
    give_up = time.time() + 2
    while len(box.sent) < 3 and time.time() < give_up:
        time.sleep(0.01)
    assert [m["to"] for m in box.sent] == ["bids@skyair.example", "rates@cloud.example", "dispo@huber.example"]
    for request in list(box.sent):
        board.deliver({"thread_id": request["thread_id"], "body": "Total: 900.00 EUR\nTransit: 2 days\nRate ID: R-1"})
    worker.join(timeout=5)
    assert [(b["carrier"], b["leg"]) for b in api.bids] == [
        ("SkyAir", "air"), ("CloudCargo", "air"), ("Huber Transporte", "pickup")]
    assert box.sent[-1]["thread_id"] == "t1"  # the quote goes into the customer's thread
    assert "quote_sent" in api.events


def test_handle_rfq_quotes_at_the_cutoff_when_carriers_stay_silent(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    started = time.time()
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), CARRIERS[:1], cutoff_s=0.2)
    assert time.time() - started < 2
    assert api.bids == []
    assert box.sent[-1]["thread_id"] == "t1"


def test_a_carrier_whose_send_fails_is_skipped_and_the_rfq_still_quotes(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))

    class PickyBox(FixtureMailbox):
        def send(self, to, subject, body):
            if to == "bids@skyair.example":
                raise RuntimeError("422 recipient not allowed")
            return super().send(to, subject, body)

    monkeypatch.setattr(rfq_agent, "PICKUP_DEADLINE_SECONDS", 0.4)  # the trucker never answers in this test
    box, api = PickyBox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), CARRIERS, cutoff_s=0.2)
    assert [m["to"] for m in box.sent][:2] == ["rates@cloud.example", "dispo@huber.example"]
    assert box.sent[-1]["thread_id"] == "t1"  # the quote still went out
    assert "quote_sent" in api.events and "error" not in api.events


def test_orchestrator_keeps_the_cheap_read_when_it_passes_the_checks(monkeypatch):
    calls = []
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model="gpt-6-luna": calls.append(model) or (RAW, 0.0001))
    read = extract_mod.read_request(MAIL)
    assert calls == ["gpt-6-luna"] and read["escalated"] is None and read["cost"] == 0.0001


def test_orchestrator_escalates_an_incomplete_read_to_the_stronger_model(monkeypatch):
    weak = {**RAW, "pieces": [{**RAW["pieces"][0], "weight": None}]}  # the cheap model missed the weight
    calls = []

    def fake(mail, model="gpt-6-luna"):
        calls.append(model)
        return (weak, 0.0001) if model == "gpt-6-luna" else (RAW, 0.001)

    monkeypatch.setattr(extract_mod, "extract", fake)
    read = extract_mod.read_request(MAIL)
    assert calls == ["gpt-6-luna", "gpt-6.1-terra"]
    assert read["missing"] == [] and read["model"] == "gpt-6.1-terra" and read["cost"] == 0.0011
    assert read["escalated"] == ["missing weight"]


def test_orchestrator_questions_dimensions_that_disagree_with_the_volume_and_survives_a_failing_escalation(monkeypatch):
    odd = {**RAW, "volume_m3": 9.9}  # 2 x 48x40x40 in = 2.0 m3, not 9.9
    def fake(mail, model="gpt-6-luna"):
        if model != "gpt-6-luna":
            raise TimeoutError("gateway")
        return odd, 0.0001
    monkeypatch.setattr(extract_mod, "extract", fake)
    read = extract_mod.read_request(MAIL)
    assert read["model"] == "gpt-6-luna" and read["rfq"]["volume_m3"] == 9.9
    assert any("m3 but the mail says 9.9" in r for r in read["escalated"])
    assert read["escalated"][-1] == "escalation failed: TimeoutError"


def test_door_to_port_waits_past_the_cutoff_for_the_first_trucker(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))  # RAW wants pickup in zone 85
    monkeypatch.setattr(rfq_agent, "PICKUP_DEADLINE_SECONDS", 3)
    box, api, board = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION}), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(MAIL, box, api, board, CARRIERS, 0.2))
    worker.start()
    give_up = time.time() + 2
    while len(box.sent) < 3 and time.time() < give_up:
        time.sleep(0.01)
    time.sleep(0.6)  # well past the 0.2 s cut-off: an airline-only RFQ would have quoted already
    trucker = next(m for m in box.sent if m["to"] == "dispo@huber.example")
    board.deliver({"thread_id": trucker["thread_id"], "body": "Total: 119.01 EUR\nTransit: 30 hours\nRate ID: TRK-1"})
    worker.join(timeout=5)
    assert [b["leg"] for b in api.bids] == ["pickup"]  # the late trucker bid made it into pricing
    assert box.sent[-1]["thread_id"] == "t1"
