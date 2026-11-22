"""Session 166: weidner.spielwaren@ (an impostor of weidner-spielwaren@) wrote "mailbox down, confirm your ORD price to
this address" and was asked a MISSING_ASK question: its earlier session 110 had an rfq but no quote, so it counted as
a known customer and the lookalike check never ran. Only a session we quoted or booked makes a sender known now."""
import pytest

import lookalike
import main
from bids import BidBoard
from inbox import FixtureMailbox
from test_lookalike import Api

REAL = "weidner-spielwaren@hackloop.mail"
IMPOSTOR = "weidner.spielwaren@hackloop.mail"
QUOTED = {"id": 101, "customer": REAL, "rfq": {"origin": "FRA", "destination": "ORD"}, "outcome": "open",
          "stage": "quoted", "quote": {"total": 2140.0, "currency": "EUR", "carrier": "Gannet Airways"}}
S166 = {"id": "m166", "thread_id": "m166", "from": IMPOSTOR, "to": "quotes@leylu.example",
        "subject": "ORD price confirmation",
        "body": "Hi, our mailbox is down at the moment. Please confirm your ORD price to this address. Thanks"}


@pytest.mark.parametrize("s110", [
    {"id": 110, "customer": IMPOSTOR, "rfq": {"origin": None, "destination": "ORD"}, "outcome": "lookalike"},
    {"id": 110, "customer": IMPOSTOR, "rfq": {"destination": "ORD", "awaiting": "missing"}, "outcome": "open",
     "stage": "pricing"},  # asked a question, no answer yet
    {"id": 110, "customer": IMPOSTOR, "rfq": {"destination": "ORD"}, "outcome": "lost", "stage": "done"},
    {"id": 110, "customer": IMPOSTOR, "rfq": {"destination": "ORD"}, "outcome": "declined"},
    {"id": 110, "customer": IMPOSTOR, "rfq": None, "outcome": "lost", "stage": "done"},
], ids=["lookalike", "open-unquoted", "lost", "declined", "no-rfq"])
def test_session_110_then_166_gets_nothing(monkeypatch, tmp_path, s110):
    monkeypatch.setattr(main, "_start", lambda handler, *a: handler(*a))
    box, api = FixtureMailbox(tmp_path), Api([QUOTED, s110])
    main.dispatch(S166, box, api, BidBoard(), [])
    assert box.sent == []  # no question, no price, nothing
    assert api.updates[-1]["outcome"] == "lost" and api.updates[-1]["stage"] == "done"
    assert any(REAL in text for _, text in api.events)


def test_the_impostors_unquoted_session_never_makes_the_real_customer_its_lookalike(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))
    s110 = {"id": 110, "customer": IMPOSTOR, "rfq": {"destination": "ORD"}, "outcome": "lookalike"}
    mail = {**S166, "from": REAL, "subject": "RFQ FRA-ORD", "body": "Please quote 3 pallets, 450 kg, FRA to ORD."}
    main.dispatch(mail, FixtureMailbox(tmp_path), Api([s110]), BidBoard(), [])
    assert started and started[0] != "decline_lookalike"


def test_known_customers():
    sessions = [QUOTED,
                {"id": 2, "customer": "a@one.example", "booking": {"booking_reference": "BK-1"}, "outcome": "won"},
                {"id": 3, "customer": "b@two.example", "quote": {"total": 900.0}, "outcome": "lost"},  # said no
                {"id": 4, "customer": IMPOSTOR, "rfq": {"destination": "ORD"}, "outcome": "open"},
                {"id": 5, "customer": "c@three.example", "quote": {"total": 1.0}, "outcome": "lookalike"},
                {"id": 6, "customer": None, "quote": {"total": 1.0}}]
    real, exempt = lookalike.known_customers(sessions)
    assert real == [REAL, "a@one.example", "b@two.example"] and exempt == [REAL, "a@one.example"]


def test_a_customer_who_said_no_is_still_protected_and_never_flagged(monkeypatch, tmp_path):
    lost = {**QUOTED, "outcome": "lost", "stage": "done"}
    real, exempt = lookalike.known_customers([lost])
    assert lookalike.imitated(S166, real, exempt) == REAL
    assert lookalike.imitated({**S166, "from": REAL}, real, exempt) is None


def test_a_quoted_sender_is_themselves(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))
    main.dispatch({**S166, "from": REAL}, FixtureMailbox(tmp_path), Api([QUOTED]), BidBoard(), [])
    assert started and started[0] != "decline_lookalike"
