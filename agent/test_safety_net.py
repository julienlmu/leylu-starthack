"""SAFETY_NET: at T+5:20 an RFQ that got nothing at all gets one last reply (the priced quote, else an honest decline).
Sessions 125 (paused, resumed at T+4:27, never quoted) and 164 (an import nobody priced) are the shapes it fires on;
everything that already got a reply, is held by a person or was closed on purpose stays as it was."""
import inspect
import time
from datetime import datetime, timezone

import pytest

import rfq_agent
import safety_net
from inbox import FixtureMailbox

CUSTOMER = "buyer@acme.example"
RFQ = {"origin": "STR", "destination": "PVG", "ask": "fastest", "language": "en", "contact_name": "Mia Lang",
       "pieces": [{"count": 4, "weight_kg": 1091.0, "length_cm": 120, "width_cm": 80, "height_cm": 100}]}
OPTION = {"carrier": "Elbflug Air Freight", "total": 3040.06, "currency": "EUR", "transit_days": 4.375,
          "rate_id": "R-1"}


def session(**fields):
    return {"id": 125, "customer": CUSTOMER, "thread_id": 7, "stage": "pricing", "outcome": "open", "paused": False,
            "needs_human": True, "quote": None, "booking": None, "bids": [], "rfq": dict(RFQ), **fields}


def mail(age_s=325):
    sent = datetime.fromtimestamp(time.time() - age_s, timezone.utc).isoformat()
    return {"id": 7, "thread_id": 7, "from": CUSTOMER, "to": "leylu@hackloop.mail", "subject": "Air freight STR-PVG",
            "body": "Please quote 4 pieces, 1091 kg, STR to PVG, fastest.", "received_at": sent, "attachments": []}


class Api:
    def __init__(self, state, events=(), price=None):
        self.state, self.log, self.updates = dict(state), list(events), []
        self.priced = price if price is not None else {"chosen": None, "options": [], "why": "No price"}

    def find(self, thread_id=None, reference=None):
        return self.state

    def session(self, session_id):
        return self.state

    def events(self, session_id):
        return self.log

    def price(self, rfq, bids=None, fallback=False):
        assert fallback
        return self.priced

    def update(self, session_id, **fields):
        self.updates.append(fields)
        self.state.update(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.log.append({"kind": kind, "text": text, "data": data})


@pytest.fixture(autouse=True)
def plain(monkeypatch):
    monkeypatch.setattr(safety_net, "ON", True)
    monkeypatch.setattr(safety_net, "_replied", set())
    monkeypatch.setattr(rfq_agent, "FALLBACK_GATE", False)
    monkeypatch.setattr(rfq_agent, "quote_text", lambda rfq, option, body=None:
                        f"Hi Mia,\n\nEUR {option['total']:,.2f} all-in with {option['carrier']}.\n\nLena")


def test_no_price_gets_the_honest_decline(tmp_path):  # session 164's shape: 0 options, nothing sent
    api, box = Api(session(rfq={**RFQ, "origin": "NRT", "destination": "HAM"})), FixtureMailbox(tmp_path)
    assert safety_net.fire(mail(), box, api) == "decline"
    assert len(box.sent) == 1 and "reliable price" in box.sent[0]["body"] and "EUR" not in box.sent[0]["body"]
    assert api.state["stage"] == "done" and api.state["outcome"] == "lost" and api.state["needs_human"] is False
    assert any("Safety net" in e["text"] and e["data"]["to"] == CUSTOMER for e in api.log)


def test_a_priced_option_is_quoted(tmp_path):  # session 125's shape: 4 options, resumed by a person, never quoted
    events = [{"kind": "intervened", "text": "Paused by a person"},
              {"kind": "intervened", "text": "Resumed: the agent handles it again"}]
    api = Api(session(), events, {"chosen": OPTION, "options": [OPTION], "why": "fastest"})
    box = FixtureMailbox(tmp_path)
    assert safety_net.fire(mail(), box, api) == "quote"
    assert len(box.sent) == 1 and "EUR 3,040.06" in box.sent[0]["body"]
    assert api.state["stage"] == "quoted" and api.state["quote"]["total"] == 3040.06
    assert api.state["quote"]["safety_net"] is True


def test_german_decline_in_the_mails_language(tmp_path):
    api, box = Api(session(rfq={**RFQ, "language": "de"})), FixtureMailbox(tmp_path)
    safety_net.fire(mail(), box, api)
    assert "verlässlichen Preis" in box.sent[0]["body"]


@pytest.mark.parametrize("fields,events", [
    ({"paused": True}, []),
    ({"quote": {"total": 1.0}}, []),
    ({"stage": "done", "outcome": "lost"}, []),  # a lookalike, spam, a decline: closed on purpose
    ({"outcome": "lost", "stage": "new"}, []),  # a weak lookalike waiting for a person: never a reply
    ({"rfq": {**RFQ, "awaiting": "missing"}}, []),  # we asked the customer (session 189)
    ({}, [{"kind": "intervened", "text": "Reply sent by a person"}]),  # session 66: a person's own quote
    ({}, [{"kind": "routed", "text": "Request only in an unreadable attachment: asked for the details in writing"}]),
    ({}, [{"kind": "needs_human", "text": "asked", "data": {"to": CUSTOMER, "body": "?"}}]),  # any mail to them
    ({}, [{"kind": "quote_sent", "text": "Quote sent"}]),
    ({"rfq": {"language": "en", "pieces": []}}, []),  # session 55: a sales pitch, nothing to answer
])
def test_never_where_something_went_out_or_nothing_was_asked(tmp_path, fields, events):
    api, box = Api(session(**fields), events, {"chosen": OPTION, "options": [OPTION]}), FixtureMailbox(tmp_path)
    assert safety_net.fire(mail(), box, api) is None
    assert box.sent == [] and api.updates == []


def test_never_after_our_own_reply_in_the_thread(tmp_path):
    box = safety_net.Recording(FixtureMailbox(tmp_path))
    box.reply(mail(), "Could you tell us the weight?")
    api = Api(session())
    assert safety_net.fire(mail(), box, api) is None and len(box.box.sent) == 1


def test_too_late_to_reach_5u(tmp_path):
    api, box = Api(session()), FixtureMailbox(tmp_path)
    assert safety_net.fire(mail(age_s=350), box, api) is None and box.sent == []


def test_off(tmp_path, monkeypatch):
    monkeypatch.setattr(safety_net, "ON", False)
    api, box = Api(session()), FixtureMailbox(tmp_path)
    assert safety_net.fire(mail(), box, api) is None and box.sent == []


def test_a_person_replying_meanwhile_stops_the_send(tmp_path):
    """Pricing takes seconds: the last look right before the send sees the person's reply."""
    api, box = Api(session(), [], {"chosen": OPTION, "options": [OPTION]}), FixtureMailbox(tmp_path)
    real_price = api.price

    def price(rfq, bids=None, fallback=False):
        api.log.append({"kind": "intervened", "text": "Reply sent by a person"})
        return real_price(rfq, bids, fallback)
    api.price = price
    assert safety_net.fire(mail(), box, api) is None and box.sent == []


def test_recording_box_keeps_the_attachment_parameter(tmp_path):
    """_reply_quote attaches the offer file only when box.reply takes `attachments`."""
    box = safety_net.Recording(FixtureMailbox(tmp_path))
    assert "attachments" in inspect.signature(box.reply).parameters
    box.reply(mail(), "quote", subject="Re: x", attachments=[{"filename": "a.pdf", "content_base64": ""}])
    assert box.box.sent[0]["attachments"] and box.box.sent[0]["subject"] == "Re: x"
    assert callable(box.fetch)  # everything else goes to the real mailbox


def test_watch_only_for_live_mail(monkeypatch, tmp_path):
    """Fixture mails carry old timestamps: the net would answer them at once, so it starts only in a live run."""
    import main
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *args: None)
    monkeypatch.setattr(main, "_watch", lambda *args: started.append(safety_net.watch))
    monkeypatch.setattr(main, "route", lambda *a: "rfq")
    monkeypatch.setattr(main, "asks_status", lambda m: False)

    class Board:
        def knows(self, t):
            return False

        def late(self, t):
            return None

    api = Api(session())
    api.find = lambda thread_id=None, reference=None: None
    api.sessions = lambda stage=None: []
    main.dispatch(mail(age_s=1), FixtureMailbox(tmp_path), api, Board(), [])
    assert safety_net.watch not in started
    started.clear()
    main.dispatch(mail(age_s=1), FixtureMailbox(tmp_path), api, Board(), [], 360)
    assert safety_net.watch in started
