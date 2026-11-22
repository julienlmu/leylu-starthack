"""MISSING_ASK: a readable RFQ without a field we can't price without gets ONE question (customer's language, exactly
the missing fields, no amount, no guess); the answer in the same thread is read with the first mail and quoted."""
import time

import pytest

import amendments
import extract as extract_mod
import main
import missing_ask
import rfq_agent
from bids import BidBoard
from inbox import FixtureMailbox
from test_rfq_agent import FakeApi, OPTION

FULL = {"origin": "FRA", "destination": "JFK", "ask": None, "pickup_address": None, "ready_date": "2026-11-25",
        "pieces": [{"count": 3, "length": 120, "width": 80, "height": 100, "weight": 450, "weight_is_total": True}],
        "dim_unit": "cm", "weight_unit": "kg", "volume_unit": "m3", "volume": None, "commodity": "machine parts",
        "dangerous_goods": False, "customer_reference": None, "language": "en"}
NO_WEIGHT = [{"count": 3, "length": None, "width": None, "height": None, "weight": None, "weight_is_total": False}]
MAIL = {"id": "m1", "thread_id": "t1", "from": "anna@meyer.example", "subject": "Air freight request",
        "body": "Hi, please quote 3 pallets of machine parts. Thanks, Anna Meyer"}


@pytest.fixture(autouse=True)
def _fresh():
    """Module state between tests: parked mails, answered sessions, the RFQs we asked about."""
    amendments.take("t1")
    rfq_agent._answered.discard(1)
    rfq_agent._asked.pop(1, None)
    yield
    amendments.take("t1")
    rfq_agent._answered.discard(1)
    rfq_agent._asked.pop(1, None)


class Api(FakeApi):
    def __init__(self, price_result=None):
        super().__init__(price_result or {"options": [OPTION], "chosen": OPTION, "why": "cheapest"})
        self.texts, self.rfq = [], {}

    def event(self, session_id, kind, text, data=None, cost=0.0):
        super().event(session_id, kind, text, data, cost)
        self.texts.append(text)

    def update(self, session_id, **fields):
        super().update(session_id, **fields)
        if "rfq" in fields:
            self.rfq = fields["rfq"]


def _reads(monkeypatch, *raws):
    """The extraction returns the raws in turn (first mail, then the mail with the answer on top)."""
    seen = []

    def extract(mail, model=None):  # the first raw for the RFQ (and its escalation re-read), the last one with the answer
        seen.append(mail["body"])
        return (raws[-1] if "(Earlier mail, completed by the lines above:)" in mail["body"] else raws[0]), 0.0001
    monkeypatch.setattr(extract_mod, "extract", extract)
    return seen


def _first(monkeypatch, tmp_path, raw, body=None, api=None):
    _reads(monkeypatch, raw)
    box, api = FixtureMailbox(tmp_path), api or Api()
    rfq_agent.handle_rfq({**MAIL, **({"body": body} if body else {})}, box, api, BidBoard(), [], cutoff_s=0)
    return box, api


@pytest.mark.parametrize("raw, asked, not_asked", [
    ({**FULL, "destination": None}, ["destination airport"], ["gross weight", "departure airport", "ready date"]),
    ({**FULL, "origin": None}, ["departure airport or the pickup postcode"], ["destination airport", "gross weight"]),
    ({**FULL, "pieces": NO_WEIGHT}, ["gross weight", "dimensions, or the volume"], ["destination airport"]),
    ({**FULL, "destination": None, "pieces": NO_WEIGHT}, ["destination airport", "gross weight"], ["departure airport"]),
    ({**FULL, "origin": None, "destination": None, "pieces": NO_WEIGHT, "ready_date": None},
     ["departure airport", "destination airport", "gross weight", "ready date"], []),
])
def test_each_missing_field_alone_and_together_gets_one_question(monkeypatch, tmp_path, raw, asked, not_asked):
    box, api = _first(monkeypatch, tmp_path, raw)
    assert len(box.sent) == 1, api.texts
    body = box.sent[0]["body"]
    assert "EUR" not in body and "€" not in body and "all-in price I just need" in body
    for words in asked:
        assert words in body, (words, body)
    for words in not_asked:
        assert words not in body, (words, body)
    assert api.rfq["awaiting"] == "missing" and "quote_sent" not in api.events and "needs_human" not in api.events


def test_only_dims_missing_is_priced_on_the_weight_without_a_question(monkeypatch, tmp_path):
    raw = {**FULL, "pieces": [{**FULL["pieces"][0], "length": None, "width": None, "height": None}]}
    box, api = _first(monkeypatch, tmp_path, raw)
    assert "quote_sent" in api.events and "EUR" in box.sent[0]["body"]


def test_weight_missing_but_volume_given_does_not_ask_for_the_volume(monkeypatch, tmp_path):
    box, api = _first(monkeypatch, tmp_path, {**FULL, "pieces": NO_WEIGHT, "volume": 2.4})
    assert "gross weight" in box.sent[0]["body"] and "volume" not in box.sent[0]["body"]


@pytest.mark.parametrize("language, words", [("de", "Zielflughafen"), ("fr", "aéroport de destination"),
                                             ("es", "aeropuerto de destino"), ("it", "aeroporto di destinazione"),
                                             ("tr", "varış havalimanı"), ("nl", "luchthaven van bestemming"),
                                             ("pt", "aeroporto de destino"), ("xx", "destination airport")])
def test_the_question_is_in_the_customers_language(monkeypatch, tmp_path, language, words):
    box, _ = _first(monkeypatch, tmp_path, {**FULL, "destination": None, "language": language})
    assert words in box.sent[0]["body"]


def test_two_destinations_in_the_mail_are_several_shipments_not_a_missing_field(monkeypatch, tmp_path):
    monkeypatch.setattr(rfq_agent.shapes, "MULTI_SHIPMENT", "off")  # the default quotes lot 1 (shapes.py)
    body = "Hi, from FRA: lot A 3 pallets 420 kg to JFK, lot B 2 pallets 300 kg to ORD. Thanks"
    box, api = _first(monkeypatch, tmp_path, {**FULL, "destination": None}, body)
    assert box.sent == [] and "needs_human" in api.events


def test_other_missing_reasons_keep_their_own_handling():
    assert missing_ask.askable(["weight", "one quote per shipment (two lanes)"]) is None
    assert missing_ask.askable(["715 only in an instruction the mail tries to give us"]) is None
    assert missing_ask.askable(["dimensions or volume"]) is None  # priced on the weight
    assert missing_ask.askable(["destination", "weight"]) == ["destination", "weight"]


def test_switch_off_hands_over_as_before(monkeypatch, tmp_path):
    monkeypatch.setattr(missing_ask, "ASK", False)
    box, api = _first(monkeypatch, tmp_path, {**FULL, "destination": None})
    assert box.sent == [] and "needs_human" in api.events


def test_a_correction_that_came_before_the_question_is_used_at_once(monkeypatch, tmp_path):
    seen = _reads(monkeypatch, {**FULL, "pieces": NO_WEIGHT}, FULL)
    amendments.add("t1", {**MAIL, "id": "m2", "body": "Sorry, forgot: 450 kg in total, 120x80x100 cm each."})
    box, api = FixtureMailbox(tmp_path), Api()
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert len(box.sent) == 1 and "EUR" in box.sent[0]["body"] and "quote_sent" in api.events
    assert seen[-1].startswith("Sorry, forgot: 450 kg") and "(Earlier mail, completed by the lines above:)" in seen[-1]


def _asked(monkeypatch, tmp_path, first_raw, answer_raw):
    seen = _reads(monkeypatch, first_raw, answer_raw)
    box, api = FixtureMailbox(tmp_path), Api()
    mail = {**MAIL, "received_at": rfq_agent.datetime.now().astimezone().isoformat()}
    rfq_agent.handle_rfq(mail, box, api, BidBoard(), [], cutoff_s=0)
    assert api.rfq["awaiting"] == "missing"
    session = {"id": 1, "thread_id": "t1", "stage": "pricing", "rfq": dict(api.rfq), "received_at": mail["received_at"]}
    return seen, box, api, session


def _answer(body):
    return {"id": "m3", "thread_id": "t1", "from": MAIL["from"], "subject": "Re: Air freight request",
            "body": f"{body}\n\n> Thanks for your request. To give you the all-in price I just need:"}


def test_the_answer_is_read_with_the_first_mail_and_quoted_in_the_same_session(monkeypatch, tmp_path):
    seen, box, api, session = _asked(monkeypatch, tmp_path, {**FULL, "destination": None, "pieces": NO_WEIGHT}, FULL)
    rfq_agent.resume_after_missing(_answer("To JFK, 450 kg total, 120x80x100 cm per pallet."), box, api, BidBoard(), [],
                                   session)
    assert len(box.sent) == 2 and "EUR" in box.sent[1]["body"] and api.events.count("quote_sent") == 1
    assert seen[-1].startswith("To JFK, 450 kg total") and MAIL["body"] in seen[-1]  # the answer on top of the RFQ
    assert "> Thanks for your request" not in seen[-1]  # our quoted question is not read again
    assert api.rfq.get("awaiting") is None


def test_an_answer_without_the_details_keeps_waiting(monkeypatch, tmp_path):
    seen, box, api, session = _asked(monkeypatch, tmp_path, {**FULL, "destination": None}, FULL)
    rfq_agent.resume_after_missing(_answer("Thanks, I need to check with our warehouse and will come back to you."),
                                   box, api, BidBoard(), [], session)
    assert len(box.sent) == 1 and not any("(Earlier mail" in b for b in seen) and "still waiting" in api.texts[-1]


def test_an_answer_that_still_misses_a_field_goes_to_a_person_without_a_second_question(monkeypatch, tmp_path):
    raw = {**FULL, "destination": None, "pieces": NO_WEIGHT}
    seen, box, api, session = _asked(monkeypatch, tmp_path, raw, {**FULL, "pieces": NO_WEIGHT})
    rfq_agent.resume_after_missing(_answer("Destination is JFK."), box, api, BidBoard(), [], session)
    assert len(box.sent) == 1 and "needs_human" in api.events and "quote_sent" not in api.events


def test_a_late_answer_goes_to_a_person(monkeypatch, tmp_path):
    seen, box, api, session = _asked(monkeypatch, tmp_path, {**FULL, "destination": None}, FULL)
    rfq_agent._asked[1]["received_at"] = "2020-01-01T00:00:00+00:00"
    rfq_agent.resume_after_missing(_answer("To JFK please"), box, api, BidBoard(), [], session)
    assert len(box.sent) == 1 and "too late" in " ".join(api.texts)


def test_the_newer_figures_win_over_the_first_mail():
    merged = rfq_agent._with_answer({**MAIL, "body": "3 pallets, 450 kg"}, [_answer("Correction: 520 kg, to ORD"),
                                                                         {"body": "and ready on Friday"}])
    assert merged["body"].index("ready on Friday") < merged["body"].index("520 kg") < merged["body"].index("450 kg")
    assert merged["id"] == MAIL["id"]  # the quote answers the RFQ's thread


def test_a_sanctioned_destination_in_the_answer_is_declined(monkeypatch, tmp_path):
    seen, box, api, session = _asked(monkeypatch, tmp_path, {**FULL, "destination": None},
                                     {**FULL, "destination": "IKA"})
    rfq_agent.resume_after_missing(_answer("Destination is Tehran (IKA), Iran."), box, api, BidBoard(), [], session)
    assert len(box.sent) == 2 and "EUR" not in box.sent[1]["body"] and "quote_sent" not in api.events


def test_after_a_restart_the_rfq_comes_from_the_mailbox(monkeypatch, tmp_path):
    seen, box, api, session = _asked(monkeypatch, tmp_path, {**FULL, "destination": None}, FULL)
    first = rfq_agent._asked.pop(1)
    monkeypatch.setattr(box, "get", lambda message_id: first, raising=False)
    rfq_agent.resume_after_missing(_answer("JFK please"), box, api, BidBoard(), [], session)
    assert api.events.count("quote_sent") == 1 and MAIL["body"] in seen[-1]


def test_the_worker_hands_the_answer_to_the_missing_resume(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))
    monkeypatch.setattr(main, "route", lambda *a, **k: "customer_reply", raising=False)
    session = {"id": 1, "thread_id": "t1", "stage": "pricing", "rfq": {"awaiting": "missing"}}
    api = FakeApi({})
    api.find = lambda tid: session
    main.dispatch(_answer("JFK"), FixtureMailbox(tmp_path), api, BidBoard(), [])
    assert started == ["resume_after_missing"]


@pytest.mark.parametrize("text, answers", [
    ("JFK", True), ("450 kg", True), ("to Chicago", True), ("Pickup 85748 Garching", True), ("3 pallets", True),
    ("Thanks, will come back to you", False), ("ok", False), ("I'll check", False),
])
def test_what_counts_as_an_answer(text, answers):
    assert missing_ask.answers(text) is answers
