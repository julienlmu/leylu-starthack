"""Traps 2 (bids, fallback, booking by email): 9 restart during a gate hold, 10 booking mail states the amount,
11 per-kg bid via the LLM reader, 15 conditional bids, 16 cheaper late bid, 17 withdrawn bid. Trap 7 is in
backend/test_overnight.py. Fakes only: no LLM, no backend, nothing sent."""
import threading
import time

import bids
import booking_agent
import main
import rfq_agent
from bids import BidBoard
from test_rfq_agent import FakeApi, MAIL, FixtureMailbox

RFQ = {"origin": "FRA", "destination": "JFK", "ask": "cheapest", "pickup": None, "ready_date": "2026-11-23",
       "pieces": [{"count": 1, "weight_kg": 500, "length_cm": 100, "width_cm": 100, "height_cm": 100}],
       "volume_m3": None, "language": "en", "contact_name": "Anna Berg", "commodity": "machine parts",
       "dangerous_goods": False}
AIR = {"name": "SkyAir", "email": "bids@skyair.example", "kind": "airline", "serves": ["*"]}
AIR2 = {"name": "CloudCargo", "email": "rates@cloud.example", "kind": "airline", "serves": ["*"]}


class DeliveringBox(FixtureMailbox):
    """Each bid request is answered by `answers[carrier email]` (a list of bodies) right after it is sent."""

    def __init__(self, folder, board, answers):
        super().__init__(folder)
        self.board, self.answers = board, answers

    def send(self, to, subject, body):
        thread_id = super().send(to, subject, body)
        for i, text in enumerate(self.answers.get(to, [])):
            threading.Timer(0.05 * (i + 1), self.board.deliver,
                            [{"thread_id": thread_id, "from": to, "body": text, "attachments": []}]).start()
        return thread_id


def _round(tmp_path, answers, targets=(AIR,), cutoff_s=0.5):
    board = BidBoard()
    box, api = DeliveringBox(tmp_path, board, answers), FakeApi({})
    mail = {**MAIL, "received_at": None}
    got, cost = rfq_agent._carrier_round(1, mail, RFQ, list(targets), box, api, board, cutoff_s)
    return got, api, board, box


# --- 11: a per-kg bid the regex can't read reaches the LLM with the chargeable weight -------------------------------

def test_11_the_llm_bid_reader_gets_the_chargeable_weight(monkeypatch):
    seen = {}

    def fake(name, system, user, schema):
        seen["user"] = user
        return {"total": 1550.0, "currency": "EUR", "transit_days": 2, "rate_id": None}, 0.00004

    monkeypatch.setattr(bids.llm, "chat_json", fake)
    bid, _ = bids.read_bid("Offer: EUR 3.10/kg incl. fuel and security, min EUR 200", 500.0)
    assert "500" in seen["user"] and "kg" in seen["user"].lower()
    assert bid["total"] == 1550.0


def test_11_a_per_kg_all_in_bid_is_priced_for_the_shipment_not_dropped(tmp_path):
    got, api, *_ = _round(tmp_path, {AIR["email"]: ["Our rate: EUR 3.10/kg all-in, transit 2 days"]})
    assert [(b["carrier"], b["total"]) for b in got] == [("SkyAir", 1550.0)]  # 500 kg chargeable


# --- 15: conditional bids are flagged and booked only after the carrier reconfirms ----------------------------------

def test_15_a_conditional_bid_is_used_but_flagged(tmp_path):
    got, api, *_ = _round(tmp_path, {AIR["email"]: ["Total: 1,450.00 EUR all-in, subject to space. Transit 2 days"]})
    assert got[0]["total"] == 1450.0 and "subject to space" in got[0]["conditional"].lower()
    assert "needs_human" not in api.events  # the quote may still use it
    assert "conditional" in str(api.data["bid"]).lower() or any("conditional" in str(u) for u in api.updates)


def test_15_a_firm_bid_is_not_flagged(tmp_path):
    got, *_ = _round(tmp_path, {AIR["email"]: ["Total: 1,450.00 EUR all-in. Transit 2 days. Rate ID: R-9"]})
    assert not got[0].get("conditional")


# --- 17 (in the round): a withdrawal drops that carrier's bid ------------------------------------------------------

def test_17_a_withdrawal_in_the_round_drops_the_bid(tmp_path):
    got, *_ = _round(tmp_path, {AIR["email"]: ["Total: 1,450.00 EUR all-in", "Sorry, we have to withdraw our offer: "
                                               "the space is gone."]},
                     targets=(AIR, AIR2), cutoff_s=0.4)
    assert got == []


# --- booking (10, 15, 17) -------------------------------------------------------------------------------------------

QUOTE = {"source": "carrier_bid", "leg": "air", "carrier": "SkyAir", "rate_id": None, "currency": "EUR",
         "total": 1450.0, "total_eur": 1450.0, "transit_days": 2, "sent_at": "2026-11-22T10:00:00+00:00"}
BID = {"source": "carrier_bid", "leg": "air", "carrier": "SkyAir", "rate_id": None, "currency": "EUR", "total": 1450.0,
       "transit_days": 2}
OTHER = {"source": "carrier_bid", "leg": "air", "carrier": "CloudCargo", "rate_id": "CC-7", "currency": "EUR",
         "total": 1600.0, "transit_days": 3}
YES = {"id": 50, "thread_id": "t1", "from": "buyer@customer.example", "subject": "Re: RFQ",
       "body": "Yes please, book it.", "received_at": None, "attachments": []}


class BookingApi:
    def __init__(self, session, book_error=None, price=None):
        self.s, self.book_error, self.price_result = session, book_error, price
        self.events, self.booked, self.priced = [], [], []

    def session(self, sid):
        return dict(self.s)

    def update(self, sid, **f):
        self.s.update(f)

    def event(self, sid, kind, text, data=None, cost=0.0):
        self.events.append((kind, text))

    def book(self, sid, rate_id):
        self.booked.append(rate_id)
        if self.book_error:
            raise self.book_error
        return {"booking_reference": "BK-1", "airline": "SkyAir", "rate_id": rate_id}

    def price(self, rfq, bids=None, fallback=False):
        self.priced.append(bids)
        return self.price_result


class EmailOnly(Exception):
    def __init__(self):
        super().__init__("portal")
        self.response = type("R", (), {"status_code": 422, "text": booking_agent.EMAIL_ONLY})()


def _session(bids_, quote=QUOTE):
    return {"id": 7, "thread_id": "t1", "customer": "buyer@customer.example", "stage": "quoted", "rfq": RFQ,
            "quote": dict(quote), "bids": [dict(b) for b in bids_], "paused": False}


def _airlines(monkeypatch):
    monkeypatch.setattr(booking_agent, "_airlines", {"skyair": "bids@skyair.example",
                                                     "cloudcargo": "rates@cloud.example"})


def test_10_the_email_booking_states_the_accepted_amount_and_our_reference(tmp_path, monkeypatch):
    _airlines(monkeypatch)
    box, api = FixtureMailbox(tmp_path), BookingApi(_session([BID]), book_error=EmailOnly())
    booking_agent.handle_customer_reply(YES, box, api, api.session(7))
    to_airline = [m for m in box.sent if m["to"] == "bids@skyair.example"]
    assert len(to_airline) == 1
    assert "EUR 1,450.00" in to_airline[0]["body"] and "S-7" in to_airline[0]["body"]


def test_15_accepting_a_conditional_bid_reconfirms_with_the_carrier_first(tmp_path, monkeypatch):
    _airlines(monkeypatch)
    session = _session([{**BID, "rate_id": "R-SKY", "conditional": "subject to space"}],
                       quote={**QUOTE, "rate_id": "R-SKY"})
    box, api = FixtureMailbox(tmp_path), BookingApi(session)
    booking_agent.handle_customer_reply(YES, box, api, api.session(7))
    assert api.booked == []  # not booked on the portal as if it were firm
    to_airline = [m for m in box.sent if m["to"] == "bids@skyair.example"]
    assert len(to_airline) == 1 and "subject to space" in to_airline[0]["body"]
    to_customer = [m for m in box.sent if m["to"] == "buyer@customer.example"]
    assert len(to_customer) == 1 and "BK-" not in to_customer[0]["body"]
    assert not (api.s.get("booking") or {}).get("booking_reference")


def test_17_accepting_a_withdrawn_bid_asks_the_customer_at_the_new_price(tmp_path, monkeypatch):
    _airlines(monkeypatch)
    new = {**OTHER, "total_eur": 1600.0}
    api = BookingApi(_session([{**BID, "withdrawn": "we have to withdraw our offer"}, OTHER]),
                     price={"options": [new], "chosen": new, "why": ""})
    box = FixtureMailbox(tmp_path)
    booking_agent.handle_customer_reply(YES, box, api, api.session(7))
    assert api.booked == [] and not any(m["to"] == "bids@skyair.example" for m in box.sent)
    assert all(b["carrier"] != "SkyAir" for b in api.priced[0])
    assert len(box.sent) == 1 and box.sent[0]["to"] == "buyer@customer.example" and "1,600" in box.sent[0]["body"]
    assert api.s["quote"]["carrier"] == "CloudCargo" and api.s["quote"]["total"] == 1600.0
    assert api.s["quote"]["rate_id"] == "CC-7" and api.s["stage"] == "quoted"


def test_17_a_withdrawn_bid_and_no_other_price_goes_to_a_person(tmp_path, monkeypatch):
    _airlines(monkeypatch)
    api = BookingApi(_session([{**BID, "withdrawn": "withdrawn"}]), price={"options": [], "chosen": None, "why": ""})
    box = FixtureMailbox(tmp_path)
    booking_agent.handle_customer_reply(YES, box, api, api.session(7))
    assert api.booked == [] and box.sent == [] and api.s.get("needs_human") is True


# --- 16, 17: replies in a bid thread after the cut-off --------------------------------------------------------------

def _late_setup():
    board = BidBoard()
    board.watch("bt1", None, AIR)
    board.forget(["bt1"], session_id=7)
    return board


def test_16_a_cheaper_bid_after_the_quote_alerts_a_person_and_sends_nothing(tmp_path):
    board = _late_setup()
    box, api = FixtureMailbox(tmp_path), BookingApi(_session([BID]))
    late = {"id": 60, "thread_id": "bt1", "from": AIR["email"], "subject": "Re: Rate request",
            "body": "Revised offer: Total 1,300.00 EUR all-in", "attachments": []}
    rfq_agent.late_bid(late, *board.late("bt1"), box, api)
    assert box.sent == []
    assert api.s.get("needs_human") is True
    assert any(k == "needs_human" and "150.00" in t for k, t in api.events)


def test_16_a_dearer_late_bid_is_only_logged(tmp_path):
    board = _late_setup()
    box, api = FixtureMailbox(tmp_path), BookingApi(_session([BID]))
    late = {"id": 61, "thread_id": "bt1", "from": AIR["email"], "subject": "Re", "body": "Total 1,700.00 EUR",
            "attachments": []}
    rfq_agent.late_bid(late, *board.late("bt1"), box, api)
    assert box.sent == [] and not api.s.get("needs_human") and api.events


def test_17_a_late_withdrawal_marks_the_bid_withdrawn(tmp_path):
    board = _late_setup()
    box, api = FixtureMailbox(tmp_path), BookingApi(_session([BID, OTHER]))
    late = {"id": 62, "thread_id": "bt1", "from": AIR["email"], "subject": "Re",
            "body": "Unfortunately our offer is no longer valid, we withdraw it.", "attachments": []}
    rfq_agent.late_bid(late, *board.late("bt1"), box, api)
    assert [b.get("withdrawn") is not None for b in api.s["bids"]] == [True, False]
    assert box.sent == [] and api.s.get("needs_human") is True


def test_16_dispatch_hands_a_late_bid_to_late_bid(monkeypatch):
    board = _late_setup()
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *args: started.append(handler.__name__))
    mail = {"id": 63, "thread_id": "bt1", "from": AIR["email"], "subject": "Re: Rate request", "body": "Total 1 EUR",
            "attachments": []}

    class Api:
        def find(self, thread_id=None, reference=None):
            return None

    main.dispatch(mail, None, Api(), board, [AIR])
    assert started == ["late_bid"]


# --- 9: a restart during a gate hold resumes the hold, not the fallback ----------------------------------------------

def test_9_resume_unfinished_resumes_a_gate_hold_not_the_fallback(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timedelta, timezone
    fresh = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    (tmp_path / "601.json").write_text(json.dumps({"id": 601, "thread_id": 601, "from": "c@x", "subject": "RFQ",
                                                   "body": "…", "received_at": fresh}))
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *args: started.append(handler.__name__))

    class Api:
        def sessions(self):
            return [{"id": 9, "thread_id": "601", "stage": "pricing", "received_at": fresh, "needs_human": True,
                     "rfq": {**RFQ, "gate_hold": True}}]

    assert main.resume_unfinished(FixtureMailbox(tmp_path), Api(), BidBoard(), []) == [9]
    assert started == ["resume_held"]


def test_9_resume_held_runs_the_gate_and_waits_for_the_hold(tmp_path, monkeypatch):
    option = {"source": "sheet", "carrier": "SkyAir", "rate_id": "R-1", "currency": "EUR", "total": 1450.0,
              "transit_days": 2, "chargeable_weight_kg": 500, "breakdown": []}
    calls = []
    monkeypatch.setattr(rfq_agent, "_gate", lambda *a: calls.append("gate") or ("GATED TEXT", option, True))
    monkeypatch.setattr(rfq_agent, "_hold", lambda *a: calls.append("hold") or True)
    api = BookingApi({"id": 9, "stage": "pricing", "needs_human": True, "paused": False, "quote": None},
                     price={"options": [option], "chosen": option, "why": ""})
    box = FixtureMailbox(tmp_path)
    session = {"id": 9, "rfq": {**RFQ, "gate_hold": True}, "bids": [BID]}
    rfq_agent.resume_held(session, {**MAIL, "received_at": None}, box, api)
    assert calls == ["gate", "hold"] and api.priced == [[BID]]
    assert len(box.sent) == 1 and "GATED TEXT" in box.sent[0]["body"]
    assert api.s["stage"] == "quoted" and api.s["quote"]["total"] == 1450.0


def test_9_the_gate_hold_is_marked_on_the_session(tmp_path, monkeypatch):
    option = {"source": "sheet", "carrier": "SkyAir", "rate_id": "R-1", "currency": "EUR", "total": 1450.0,
              "transit_days": 2, "chargeable_weight_kg": 500, "breakdown": []}
    monkeypatch.setattr(rfq_agent, "_gate", lambda *a: ("TEXT", option, True))
    monkeypatch.setattr(rfq_agent, "_hold", lambda *a: False)  # a person took over
    api = FakeApi({"options": [option], "chosen": option, "why": ""})
    rfq_agent._price_and_quote(1, {**MAIL, "received_at": None}, dict(RFQ), 0.0, FixtureMailbox(tmp_path), api,
                               BidBoard(), [], 0)
    assert any((u.get("rfq") or {}).get("gate_hold") for u in api.updates)
