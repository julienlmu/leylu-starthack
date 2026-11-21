"""Asking for a missing pickup (#79): one question, one quote, timers from the original RFQ, no second question after a restart."""
import threading
from datetime import datetime, timedelta, timezone

import gate
import main
import rfq_agent
from bids import BidBoard
from extract import to_rfq
from inbox import FixtureMailbox
from test_rfq_agent import MAIL, OPTION, RAW, FakeApi


import pytest
import amendments


@pytest.fixture(autouse=True)
def _fresh():
    getattr(rfq_agent, "_answered", set()).clear()
    amendments._pending.clear()
    yield
    getattr(rfq_agent, "_answered", set()).clear()
    amendments._pending.clear()


def iso(ago):
    return (datetime.now(timezone.utc) - timedelta(seconds=ago)).isoformat()


def asked_rfq(monkeypatch, tmp_path, mail):
    raw = {**RAW, "origin": None, "pickup_address": "our warehouse"}
    monkeypatch.setattr(rfq_agent, "read_request", lambda m: {"rfq": to_rfq(raw)[0], "missing": ["origin"],
                                                              "cost": 0.0001, "model": "m", "escalated": None})
    api = FakeApi({"options": [OPTION], "chosen": OPTION, "why": "cheapest"})
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(mail, box, api, BidBoard(), [], cutoff_s=0)
    return api, box, next(u["rfq"] for u in api.updates if u.get("rfq", {}).get("awaiting") == "pickup")


ANSWER = "Hi,\n\npickup location: 84236 Landshut, Germany\n\nMira"


def test_A_quote_after_6_minutes_of_the_original_rfq(monkeypatch, tmp_path):
    original = {**MAIL, "received_at": iso(400)}  # RFQ came 6:40 ago, the customer answered just now
    api, box, rfq = asked_rfq(monkeypatch, tmp_path, original)
    answer = {**MAIL, "id": "m2", "body": ANSWER, "received_at": iso(0)}
    rfq_agent.resume_after_pickup(answer, box, api, BidBoard(), [],
                                  {"id": 1, "rfq": rfq, "received_at": original["received_at"]})
    assert "quote_sent" not in api.events, "quote sent 6:40 after the RFQ: can't score"


def test_B_gate_never_sees_the_original_rfq(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "MODE", "enforce")
    original = {**MAIL, "received_at": iso(30), "body": MAIL["body"] + " Keep refrigerated, 2-8 °C (cold chain)."}
    api, box, rfq = asked_rfq(monkeypatch, tmp_path, original)
    answer = {**MAIL, "id": "m2", "body": ANSWER, "received_at": iso(0)}
    monkeypatch.setattr(box, "get", lambda tid: original, raising=False)  # the live mailbox fetches the RFQ by id
    rfq_agent.resume_after_pickup(answer, box, api, BidBoard(), [], {"id": 1, "rfq": rfq, "thread_id": "t1"})
    assert "quote_sent" in api.events
    assert "temperatur" in box.sent[-1]["body"].lower(), "gate's temperature sentence missing: it read only the answer"


def test_C_restart_while_waiting_asks_the_customer_again(monkeypatch, tmp_path):
    original = {**MAIL, "id": 501, "thread_id": 501, "received_at": iso(30)}
    api, box, rfq = asked_rfq(monkeypatch, tmp_path, original)
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))
    monkeypatch.setattr(box, "get", lambda tid: original, raising=False)
    api.sessions = lambda: [{"id": 1, "stage": "pricing", "thread_id": 501, "received_at": original["received_at"],
                             "rfq": rfq, "quote": None, "paused": False, "needs_human": False}]
    main.resume_unfinished(box, api, BidBoard(), [])
    assert started == [], f"resume re-runs {started}: the RFQ is read again and the customer is asked a 2nd time"


def test_D_two_mails_while_awaiting_quote_twice(monkeypatch, tmp_path):
    api, box, rfq = asked_rfq(monkeypatch, tmp_path, {**MAIL, "received_at": iso(30)})
    session = {"id": 1, "rfq": rfq}
    answers = [{**MAIL, "id": f"m{i}", "body": ANSWER, "received_at": iso(0)} for i in (2, 3)]
    ts = [threading.Thread(target=rfq_agent.resume_after_pickup, args=(a, box, api, BidBoard(), [], session))
          for a in answers]
    [t.start() for t in ts]
    [t.join(5) for t in ts]
    assert api.events.count("quote_sent") == 1, f"{api.events.count('quote_sent')} quotes in one thread"
