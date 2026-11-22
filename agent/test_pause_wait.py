"""PAUSE_WAIT (R120): paused at the send, resumed later, the quote still goes out; never after a person's reply."""
import time

import pause_wait
import rfq_agent
from bids import BidBoard
from extract import to_rfq
from inbox import FixtureMailbox
from test_rfq_agent import MAIL, OPTION, RAW, FakeApi


class Clock:
    def __init__(self, monkeypatch):
        self.t = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: self.t)
        monkeypatch.setattr(pause_wait, "_sleep", self.sleep)

    def sleep(self, s):
        self.t += s


class PausedThenResumed(FakeApi):
    """Paused for the first `paused_polls` looks, then resumed; `by_hand`: a person replied while paused."""
    def __init__(self, result, paused_polls, by_hand=False, quote_by_hand=False):
        super().__init__(result)
        self.kinds = self.__dict__.pop("events")  # FakeApi keeps event kinds in .events; the backend's events() is a call
        self.looks, self.paused_polls, self.by_hand, self.quote_by_hand = 0, paused_polls, by_hand, quote_by_hand

    def session(self, session_id):
        self.looks += 1
        paused = self.looks <= self.paused_polls
        quote = {"total": 1.0} if self.quote_by_hand and not paused else None
        return {"paused": paused, "needs_human": False, "quote": quote}

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.kinds.append(kind)
        self.data[kind] = data

    def events(self, session_id):
        return [{"kind": "intervened", "text": "Reply sent by a person"}] if self.by_hand else []


def _run(tmp_path, monkeypatch, api):
    monkeypatch.setattr(rfq_agent, "read_request",
                        lambda mail: {"rfq": to_rfq(RAW)[0], "missing": [], "cost": 0.0001, "model": "m", "escalated": None})
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    return box


def test_a_resume_after_a_pause_at_the_send_still_sends_the_quote(tmp_path, monkeypatch):
    Clock(monkeypatch)
    api = PausedThenResumed({"options": [OPTION], "chosen": OPTION}, paused_polls=40)
    box = _run(tmp_path, monkeypatch, api)
    assert len(box.sent) == 1 and "quote_sent" in api.kinds


def test_no_quote_when_a_person_answered_the_customer_while_paused(tmp_path, monkeypatch):
    Clock(monkeypatch)
    api = PausedThenResumed({"options": [OPTION], "chosen": OPTION}, paused_polls=40, by_hand=True)
    assert _run(tmp_path, monkeypatch, api).sent == []


def test_no_quote_when_a_person_quoted_by_hand(tmp_path, monkeypatch):
    Clock(monkeypatch)
    api = PausedThenResumed({"options": [OPTION], "chosen": OPTION}, paused_polls=40, quote_by_hand=True)
    assert _run(tmp_path, monkeypatch, api).sent == []


def test_no_quote_when_still_paused_when_the_rfq_runs_out(tmp_path, monkeypatch):
    Clock(monkeypatch)
    api = PausedThenResumed({"options": [OPTION], "chosen": OPTION}, paused_polls=10_000)
    assert _run(tmp_path, monkeypatch, api).sent == []
    assert api.kinds[-1] == "needs_human"


def test_unreadable_events_never_risk_a_second_mail(monkeypatch):
    Clock(monkeypatch)

    class Broken(PausedThenResumed):
        def events(self, session_id):
            raise OSError("backend down")

    api = Broken({}, paused_polls=3)
    assert pause_wait.cleared(1, time.time(), api) is False


def test_off_keeps_the_old_behaviour(monkeypatch):
    Clock(monkeypatch)
    monkeypatch.setattr(pause_wait, "ON", False)
    assert pause_wait.cleared(1, time.time(), PausedThenResumed({}, paused_polls=3)) is False


def test_a_resume_during_a_gate_hold_sends_the_held_quote(monkeypatch):
    clock = Clock(monkeypatch)
    monkeypatch.setattr(rfq_agent, "_sleep", clock.sleep)
    api = PausedThenResumed({}, paused_polls=5)
    assert rfq_agent._wait_held(1, clock.t + 200, api, clock.t) is True
    api = PausedThenResumed({}, paused_polls=5, by_hand=True)
    assert rfq_agent._wait_held(1, clock.t + 200, api, clock.t) is False
