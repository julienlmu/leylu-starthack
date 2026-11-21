"""Orderings for the fallback quote (#68): a person who answers while it prices always wins, nothing after 5:30."""
import rfq_agent
from test_rfq_agent import FakeApi, MAIL, OPTION, RAW, FixtureMailbox, BidBoard, to_rfq


def _setup(monkeypatch):
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(rfq_agent, "read_request", lambda mail: {"rfq": to_rfq(RAW)[0], "missing": [], "cost": 0.0001,
                                                                 "model": "m", "escalated": None})


class Stateful(FakeApi):
    """Session state as the backend keeps it; a person's /intervene send can complete during fallback pricing."""
    def __init__(self, *a, person=None):
        super().__init__(*a)
        self.state = {"paused": False, "quote": None, "needs_human": False}
        self.person = person

    def session(self, sid):
        return dict(self.state)

    def update(self, sid, **f):
        super().update(sid, **f)
        self.state.update({k: v for k, v in f.items() if k in self.state})

    def price(self, rfq, bids=None, fallback=False):
        if fallback and self.person:
            self.person(self.state)
        return super().price(rfq, bids, fallback)


def manual_quote_send(state):  # intervene send "EUR 1,607.38": ends with paused False, needs_human False, quote set
    state.update(paused=False, needs_human=False, quote={"total": 1607.38, "by": "person"})


def manual_plain_send(state):  # "let me check": paused True, needs_human False, no quote
    state.update(paused=True, needs_human=False)


def test_manual_quote_during_fallback_pricing_blocks_the_fallback(monkeypatch, tmp_path):
    _setup(monkeypatch)
    api = Stateful({"options": [], "chosen": None, "why": ""}, person=manual_quote_send)
    api.fallback_result = {"options": [OPTION], "chosen": OPTION, "why": "earlier bid"}
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert box.sent == [], "fallback quote went out after a person already quoted"


def test_plain_manual_reply_during_fallback_pricing_blocks_the_fallback(monkeypatch, tmp_path):
    _setup(monkeypatch)
    api = Stateful({"options": [], "chosen": None, "why": ""}, person=manual_plain_send)
    api.fallback_result = {"options": [OPTION], "chosen": OPTION, "why": "earlier bid"}
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert box.sent == []


def test_fallback_stores_a_bookable_quote(monkeypatch, tmp_path):
    _setup(monkeypatch)
    api = Stateful({"options": [], "chosen": None, "why": ""})
    api.fallback_result = {"options": [OPTION], "chosen": OPTION, "why": "earlier bid"}
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert len(box.sent) == 1 and api.updates[-1]["stage"] == "quoted"
    assert api.state["quote"]["rate_id"] == OPTION["rate_id"] and not api.state["needs_human"] and not api.state["paused"]


def test_missing_data_never_gets_a_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    rfq, _ = to_rfq(RAW)
    monkeypatch.setattr(rfq_agent, "read_request", lambda mail: {"rfq": rfq, "missing": ["weight"], "cost": 0.0001,
                                                                 "model": "m", "escalated": None})
    api = Stateful({"options": [OPTION], "chosen": OPTION, "why": ""})
    api.fallback_result = {"options": [OPTION], "chosen": OPTION, "why": "earlier bid"}
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert box.sent == [] and not getattr(api, "fallback", False)


def test_paused_before_the_timer_gets_no_fallback(monkeypatch, tmp_path):
    _setup(monkeypatch)
    api = Stateful({"options": [], "chosen": None, "why": ""})
    api.state["paused"] = True  # the person paused during the carrier round
    api.fallback_result = {"options": [OPTION], "chosen": OPTION, "why": "earlier bid"}
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert box.sent == []


def test_no_fallback_once_the_rfq_is_about_to_expire(monkeypatch, tmp_path):
    _setup(monkeypatch)
    monkeypatch.setattr(rfq_agent, "FALLBACK_LATEST_SECONDS", -1)  # as if 5:30 had passed while it priced
    api = Stateful({"options": [], "chosen": None, "why": ""})
    api.state["needs_human"] = True
    api.fallback_result = {"options": [OPTION], "chosen": OPTION, "why": "earlier bid"}
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert box.sent == []
