"""R105: "same shipment as in my earlier request 'Air freight quote request: STR to MEL' sent on 2026-11-21 at 23:18
UTC", new destination LAX: the earlier request is found by subject and/or day and time (repeat.earlier), its pieces,
weight, volume and pickup are kept, the new fields win, and it is quoted."""
import pytest

import extract as extract_mod
import repeat
import rfq_agent
from inbox import FixtureMailbox
from test_repeat import EMPTY, History
from test_rfq_agent import OPTION

ME = "Laura Klein <laura@klein-tools.example>"
PICKUP = {"address": "Industriestr. 5, 70565 Stuttgart", "zone": "70"}
STR_MEL = {"origin": "STR", "destination": "MEL", "ask": "cheapest", "pickup": PICKUP, "volume_m3": 1.8,
           "commodity": "power tools", "dangerous_goods": False,
           "pieces": [{"count": 4, "length_cm": 120, "width_cm": 80, "height_cm": 95, "weight_kg": 162.5}]}
STR_JFK = {**STR_MEL, "destination": "JFK", "pickup": None, "volume_m3": 0.6,
           "pieces": [{"count": 1, "length_cm": 100, "width_cm": 80, "height_cm": 75, "weight_kg": 240}]}
SUBJECT = "Air freight quote request: STR to MEL"
HISTORY = [
    {"id": 90, "customer": "laura@klein-tools.example", "received_at": "2026-11-21T23:18:22+00:00", "subject": SUBJECT,
     "rfq": STR_MEL, "quote": {"rate_id": None, "total": 2100.0}, "booking": None},  # quoted only
    {"id": 96, "customer": "laura@klein-tools.example", "received_at": "2026-11-22T00:40:05+00:00",
     "subject": "Quote STR-JFK", "rfq": STR_JFK, "quote": {"total": 900.0}, "booking": {"booking_reference": "BK-777"}},
    {"id": 97, "customer": "someone@else.example", "received_at": "2026-11-21T23:18:00+00:00", "subject": SUBJECT,
     "rfq": {**STR_MEL, "destination": "SYD"}, "booking": None},
]
R105 = ("Hello, please quote the same shipment as in my earlier request 'Air freight quote request: STR to MEL' sent on "
        "2026-11-21 at 23:18 UTC. This time it goes to Los Angeles (LAX), ready 2026-11-29. Thanks, Laura")
NOW = "2026-11-22T01:15:00+00:00"


def _earlier(text, history=HISTORY):
    return repeat.earlier(History(None, history), ME, 105, text, NOW)


def test_r105_phrasing_asks_for_a_repeat():
    for text in [R105, "same as my previous request from 21.11.", "Same goods as our earlier request \"STR to MEL\"",
                 "identical to the request we sent on 21 Nov", "like last week's shipment", "repeat of last week's order",
                 "same cargo as in our request of yesterday", "wie in meiner Anfrage vom 21.11.2026",
                 "same as your offer S-90"]:
        assert repeat.asks(text), text
    for text in ["Last order was damaged, new request: 2 pallets", "same day pickup", "our last shipment arrived late",
                 "Please quote 3 pallets as requested by our customer"]:
        assert not repeat.asks(text), text


def test_r105_subject_and_time_pick_that_request_not_the_latest_booked_one():
    old, why = _earlier(R105)
    assert old["id"] == 90 and why == ""  # not #96 (booked, later), not #97 (another sender with the same subject)


@pytest.mark.parametrize("text, session", [
    ("same as my earlier request 'Air freight quote request: STR to MEL', but to LAX", 90),  # subject only
    ("same as my earlier request “Air freight quote request: STR to MEL”", 90),  # curly quotes
    ("same shipment as my request from 21.11.2026, to LAX now", 90),  # day only
    ("same shipment as my request from 21 Nov", 90),
    ("same shipment as my request from November 22nd", 96),
    ("same as my request of yesterday", 90),
    ("same as in my earlier request 'Quote STR to MEL' please", 90),  # subject retyped: its lane still tells
    ("same as my earlier request sent at 00:40", 96),  # time only
    ("same as last week's request", 96),  # no day / subject: the last one, booked first
    ("same as your offer S-90, but to LAX", 90),  # our quote reference, quoted only
])
def test_variants(text, session):
    old = (repeat.by_reference(History(None, HISTORY), ME, 105, repeat.reference(text))[0] if repeat.reference(text)
           else _earlier(text)[0])
    assert old and old["id"] == session, text


def test_a_named_request_that_does_not_exist_is_never_guessed():
    old, why = _earlier("same as my earlier request 'Air freight quote request: FRA to NRT'")
    assert old is None and "no request of this sender" in why
    old, why = _earlier("same shipment as my request from 18.11.2026")
    assert old is None and "sent none then" in why
    assert _earlier(R105, [HISTORY[2]])[0] is None  # only another sender has it


def test_same_subject_and_day_twice_is_a_person_not_the_booked_one_as_a_guess():
    again = {**HISTORY[0], "id": 93, "received_at": "2026-11-21T23:50:00+00:00", "booking": {"booking_reference": "BK-93"}}
    old, why = _earlier("same as my earlier request 'Air freight quote request: STR to MEL'", [HISTORY[0], again])
    assert old is None and "2 requests" in why
    # the time named decides between them
    assert _earlier(R105, [HISTORY[0], again])[0]["id"] == 90


def test_subject_from_the_first_incoming_mail_event():
    class Api:
        def sessions(self):
            return [{**HISTORY[0], "subject": None}]

        def events(self, session_id):
            return [{"kind": "routed", "text": "x"}, {"kind": "mail_in", "text": f"RFQ from x: {SUBJECT}",
                                                       "data": {"subject": "Re: " + SUBJECT}}]
    assert repeat.earlier(Api(), ME, 105, "same as my earlier request 'Air freight quote request: STR to MEL'", NOW)[0]


@pytest.mark.parametrize("origin", ["STR", None])
def test_r105_is_quoted_with_the_old_pieces_and_pickup_and_the_new_destination(tmp_path, monkeypatch, origin):
    raw = {**EMPTY, "origin": origin, "destination": "LAX", "ready_date": "2026-11-29"}
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    box = FixtureMailbox(tmp_path)
    api = History({"options": [OPTION], "chosen": OPTION, "why": "cheapest"}, HISTORY)
    rfq_agent.handle_rfq({"id": "m105", "thread_id": "t105", "from": ME, "subject": "New request", "body": R105,
                          "received_at": NOW}, box, api)
    rfq = api.data["extracted"]
    assert (rfq["origin"], rfq["destination"], rfq["ready_date"]) == ("STR", "LAX", "2026-11-29")
    assert rfq["pieces"] == STR_MEL["pieces"] and rfq["volume_m3"] == 1.8 and rfq["pickup"] == PICKUP
    assert "quote_sent" in api.events and len(box.sent) == 1 and "needs_human" not in api.events
    assert any("Repeat of session #90" in t for t in api.texts)


def test_the_new_ready_or_pickup_date_is_no_hint_for_the_earlier_request():
    for text in ["Ready on 2026-11-29. Same shipment as my earlier request please, to LAX.",
                 "same as my last order, pickup 25.11., 2 sets of parts", "Same as last time, deliver by 3 Dec",
                 "same as our last order please, ready Wednesday", "same as last time, pick-up on Friday"]:
        assert not {"day", "clock"} & set(repeat.hints(text, NOW)), text
        assert _earlier(text)[0]["id"] == 96, text  # the last one (booked first), as before


def _at(sid, when, subject=SUBJECT):
    return {**HISTORY[0], "id": sid, "received_at": when, "subject": subject}


def test_same_subject_on_two_days_needs_the_day():
    history = [_at(80, "2026-11-17T09:00:00+00:00"), _at(90, "2026-11-21T23:18:22+00:00")]
    old, why = _earlier("same as my earlier request 'Air freight quote request: STR to MEL'", history)
    assert old is None and "2 requests" in why  # never the latest as a guess
    assert _earlier("same as my earlier request 'Air freight quote request: STR to MEL' from Tuesday", history)[0]["id"] == 80
    assert _earlier("same as my earlier request 'Air freight quote request: STR to MEL' from 21.11.", history)[0]["id"] == 90


def test_a_subject_only_another_customer_used_is_never_taken():
    history = [HISTORY[1], HISTORY[2]]  # mine: STR-JFK only; the STR-MEL subject is someone else's
    old, why = _earlier("same as my earlier request 'Air freight quote request: STR to MEL'", history)
    assert old is None and "no request of this sender" in why


def test_tuesday_when_last_tuesday_had_none():
    history = [_at(80, "2026-11-16T10:00:00+00:00"), _at(81, "2026-11-19T10:00:00+00:00")]  # Monday, Thursday
    old, why = _earlier("same as my request from Tuesday", history)
    assert old is None and "2026-11-17" in why
    assert _earlier("same as my request from Tuesday", [*history, _at(82, "2026-11-17T13:30:00+00:00")])[0]["id"] == 82


@pytest.mark.parametrize("text, session", [
    ("same as my request from Tuesday at 14:30", 82),  # 14:30 in Stuttgart = 13:30 UTC
    ("same as my request from Tuesday at 14:30 CET", 82),
    ("same as my request from Tuesday at 13:30 UTC", 82),
    ("same as my request from Tuesday at 14:30 UTC", None),  # a zone named: no other offset tried
    ("same as my request of 18.11. 00:30 CET", 83),  # 17.11. 23:30 UTC, already the 18th in Stuttgart
    ("same as my request of 18.11.", 83),
])
def test_a_time_in_the_customers_zone(text, session):
    history = [_at(80, "2026-11-16T10:00:00+00:00"), _at(82, "2026-11-17T13:30:00+00:00"),
               _at(83, "2026-11-17T23:30:00+00:00")]
    old = _earlier(text, history)[0]
    assert (old and old["id"]) == session, text


def test_an_ambiguous_named_request_goes_to_a_person_without_a_quote(tmp_path, monkeypatch):
    raw = {**EMPTY, "destination": "LAX"}
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    box = FixtureMailbox(tmp_path)
    history = [_at(80, "2026-11-17T09:00:00+00:00"), _at(90, "2026-11-21T23:18:22+00:00")]
    api = History({"options": [OPTION], "chosen": OPTION, "why": "cheapest"}, history)
    rfq_agent.handle_rfq({"id": "m106", "thread_id": "t106", "from": ME, "subject": "New request", "received_at": NOW,
                          "body": "Same goods as our earlier request 'Air freight quote request: STR to MEL', to LAX."},
                         box, api)
    assert "needs_human" in api.events and not box.sent


S201 = ("Hi there,\n\nHope your week's going well! I need to send the same shipment again, this time to LAX instead of "
        "MEL.\n\nThe previous request was \"Air freight quote request: STR to MEL\", sent on 2026-11-21 at 23:18 UTC, for "
        "MEL. The cargo and pickup details are unchanged, so you already have them from that request.\n\nIt'll be ready "
        "for pickup on 2026-11-29. Could you send me an all-in price in EUR for the cheapest option to LAX?\n\nThanks!")


def test_same_shipment_again_wording():  # sessions 119, 189, 201: asked for the weight, the answer was that request's
    for text in [S201, "Could you quote the same shipment again? My earlier request, \"Air freight quote to YYZ\", was sent "
                 "on 2026-11-21 at 23:31 UTC", "The cargo and pickup details are unchanged and you have them",
                 "Could you please quote the same shipment again, this time to YYZ?"]:
        assert repeat.asks(text), text
    for text in ["The shipment again got delayed last week, new request: 2 pallets", "same cargo details as listed below",
                 "Our previous request was cancelled. New request: 3 pallets"]:
        assert not repeat.asks(text), text
    old, why = _earlier(S201)
    assert old["id"] == 90 and why == ""


def test_same_shipment_again_is_quoted_without_a_question(tmp_path, monkeypatch):
    raw = {**EMPTY, "destination": "LAX", "ready_date": "2026-11-29"}
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    box = FixtureMailbox(tmp_path)
    api = History({"options": [OPTION], "chosen": OPTION, "why": "cheapest"}, HISTORY)
    rfq_agent.handle_rfq({"id": "m201", "thread_id": "t201", "from": ME, "subject": "Air freight quote to LAX",
                          "body": S201, "received_at": NOW}, box, api)
    rfq = api.data["extracted"]
    assert rfq["pieces"] == STR_MEL["pieces"] and rfq["origin"] == "STR" and rfq["destination"] == "LAX"
    assert "quote_sent" in api.events and len(box.sent) == 1
