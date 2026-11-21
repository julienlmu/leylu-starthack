"""FOLLOW_UP: one reminder (no amount) when a quote got no answer 2:30 later; a yes to it books as usual."""

import time
from datetime import datetime, timezone

import pytest

import follow_up
from booking_agent import handle_customer_reply
from inbox import FixtureMailbox


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


T0 = time.time() - 160  # the quote went out 160 s ago
QUOTE = {"carrier": "SkyAir", "rate_id": "R-1", "currency": "EUR", "total": 1856.0, "transit_days": 2,
         "sent_at": _iso(T0), "valid_until": "2099-11-30"}
SESSION = {"id": 17, "customer": "anna@customer.example", "thread_id": 101, "stage": "quoted", "outcome": "open",
           "needs_human": False, "paused": False, "booking": None, "llm_cost_usd": 0.0001,
           "rfq": {"origin": "MUC", "destination": "JFK", "contact_name": "Anna Sonnberg", "language": "en"},
           "quote": QUOTE}
EVENTS = [{"kind": "mail_in"}, {"kind": "extracted"}, {"kind": "priced"},
          {"kind": "quote_sent", "data": {"from": "team@forwarder.example", "subject": "Re: RFQ MUC-JFK"}}]


class Api:
    def __init__(self, session=SESSION, events=EVENTS):
        self.s, self.ev, self.booked = {**session, "quote": dict(session["quote"])}, [dict(e) for e in events], []

    def sessions(self, stage=None):
        return [self.s] if stage in (None, self.s["stage"]) else []

    def session(self, session_id):
        return self.s

    def events(self, session_id):
        return self.ev

    def update(self, session_id, **fields):
        self.s.update(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.ev.append({"kind": kind, "text": text, "data": data or {}})

    def book(self, session_id, rate_id):
        self.booked.append(rate_id)
        return {"booking_reference": "BK-1A2B3C4D", "airline": "SkyAir", "rate_id": rate_id}


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(follow_up, "FOLLOW_UP", True)
    follow_up._sent.clear()
    follow_up._replied.clear()


def test_a_silent_customer_gets_one_reminder_without_an_amount_and_only_one():
    api, box = Api(), FixtureMailbox("fixtures/inbox")
    assert follow_up.sweep(box, api) == [17]
    mail = box.sent[0]
    assert mail["to"] == "anna@customer.example" and mail["thread_id"] == 101 and mail["subject"] == "Re: RFQ MUC-JFK"
    assert mail["body"].startswith("Hi Anna,") and "book it with SkyAir" in mail["body"]
    assert "EUR" not in mail["body"] and "1,856" not in mail["body"] and "valid until 30 November" in mail["body"]
    assert api.s["quote"]["follow_up_sent_at"] and api.ev[-1]["data"]["follow_up"]
    assert follow_up.sweep(box, api) == [] and len(box.sent) == 1


def test_the_stored_flag_survives_a_restart():
    api, box = Api(), FixtureMailbox("fixtures/inbox")
    follow_up.sweep(box, api)
    follow_up._sent.clear()  # a new worker process
    assert follow_up.sweep(box, api) == [] and len(box.sent) == 1


def test_switched_off_by_default_sends_nothing(monkeypatch):
    monkeypatch.setattr(follow_up, "FOLLOW_UP", False)
    box = FixtureMailbox("fixtures/inbox")
    assert follow_up.sweep(box, Api()) == [] and box.sent == []


@pytest.mark.parametrize("age", [100, 1000])
def test_too_early_or_too_late(age):
    api = Api({**SESSION, "quote": {**QUOTE, "sent_at": _iso(time.time() - age)}})
    assert follow_up.sweep(FixtureMailbox("fixtures/inbox"), api) == []


@pytest.mark.parametrize("change", [
    {"stage": "done", "outcome": "lost"},                     # declined, or the phishing refusal
    {"stage": "booked"}, {"paused": True}, {"needs_human": True},
    {"rfq": {**SESSION["rfq"], "dangerous_goods": True}},    # DG: waits for the papers
    {"quote": {**QUOTE, "sent_at": None}},                    # a person quoted by hand
    {"quote": {**QUOTE, "asked_at": time.time()}},            # we asked about a new price
    {"quote": {**QUOTE, "fallback": True}},                   # fallback quote after a hand-over
    {"booking": {"pending_email": "air@x.example"}},
])
def test_no_reminder_on_sessions_that_are_not_a_plain_open_quote(change):
    box = FixtureMailbox("fixtures/inbox")
    assert follow_up.sweep(box, Api({**SESSION, **change})) == [] and box.sent == []


@pytest.mark.parametrize("later", ["mail_in", "intervened", "declined", "accepted"])
def test_no_reminder_once_the_customer_or_a_person_answered(later):
    box = FixtureMailbox("fixtures/inbox")
    assert follow_up.sweep(box, Api(events=EVENTS + [{"kind": later}])) == [] and box.sent == []


def test_no_reminder_after_a_gate_hold_or_an_error():
    box = FixtureMailbox("fixtures/inbox")
    held = EVENTS[:3] + [{"kind": "needs_human", "text": "Quote held by the gate"}] + EVENTS[3:]
    assert follow_up.sweep(box, Api(events=held)) == [] and box.sent == []


def test_a_reply_the_worker_routed_but_has_not_logged_yet_stops_it():
    follow_up.saw_reply(101)
    box = FixtureMailbox("fixtures/inbox")
    assert follow_up.sweep(box, Api()) == [] and box.sent == []


def test_german_customer_gets_it_in_german():
    api, box = Api({**SESSION, "rfq": {**SESSION["rfq"], "language": "de"}}), FixtureMailbox("fixtures/inbox")
    follow_up.sweep(box, api)
    body = box.sent[0]["body"]
    assert body.startswith("Hallo Anna,") and "bei SkyAir buchen" in body and "bis zum 30. November" in body


def test_a_portal_rate_expiry_is_no_promise():
    api = Api({**SESSION, "quote": {**QUOTE, "valid_until": "2099-11-21T21:05:00+00:00"}})
    box = FixtureMailbox("fixtures/inbox")
    follow_up.sweep(box, api)
    assert "valid until" not in box.sent[0]["body"]


def test_a_yes_to_the_reminder_books_through_the_normal_flow():
    api, box = Api(), FixtureMailbox("fixtures/inbox")
    follow_up.sweep(box, api)
    yes = {"id": 110, "thread_id": 101, "from": "anna@customer.example", "subject": "Re: RFQ MUC-JFK",
           "body": "Yes, go ahead.\n\nOn Sat, team wrote:\n> shall I go ahead and book it with SkyAir for you?"}
    handle_customer_reply(yes, box, api, api.s)
    assert api.booked == ["R-1"] and api.s["stage"] == "booked"


def test_the_reminder_alone_never_books():
    api = Api()
    follow_up.sweep(FixtureMailbox("fixtures/inbox"), api)
    assert api.booked == [] and api.s["stage"] == "quoted"
