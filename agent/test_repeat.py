"""'Same as our last order': the gaps are filled from the sender's previous request in the CRM (repeat.py)."""
import extract as extract_mod
import repeat
import rfq_agent
from inbox import FixtureMailbox
from test_rfq_agent import FakeApi, OPTION

OLD = {"origin": "FRA", "destination": "ORD", "ask": "fastest", "pickup": None, "volume_m3": 2.4, "commodity": "pumps",
       "pieces": [{"count": 3, "length_cm": 120, "width_cm": 80, "height_cm": 100, "weight_kg": 213.3}],
       "dangerous_goods": False, "excluded_airlines": ["Zephyr Steppe Cargo"], "offer_doc": "pdf"}
EMPTY = {"origin": None, "destination": None, "ask": None, "pickup_address": None, "ready_date": "2026-11-25",
         "pieces": [{"count": 1, "length": None, "width": None, "height": None, "weight": None, "weight_is_total": False}],
         "dim_unit": "cm", "weight_unit": "kg", "volume_unit": "m3", "volume": None, "commodity": None,
         "dangerous_goods": False, "customer_reference": None, "language": "en"}
MAIL = {"id": "m9", "thread_id": "t9", "from": "Anna Meyer <ANNA@meyer.example>", "subject": "New shipment",
        "body": "Hi, same as our last order please, ready Wednesday. Thanks, Anna"}


class History(FakeApi):
    def __init__(self, price_result, sessions):
        super().__init__(price_result)
        self.history, self.texts = sessions, []

    def sessions(self, stage=None):
        return self.history

    def event(self, session_id, kind, text, data=None, cost=0.0):
        super().event(session_id, kind, text, data, cost)
        self.texts.append(text)


def test_phrasings():
    for text in ["Same as our last order", "just like my previous shipment", "like last time", "the usual please",
                 "Wie beim letzten Mal", "wie unsere letzte Sendung", "comme la dernière fois",
                 "come l'ultima volta", "como la última vez", "geçen seferki gibi", "zoals vorige keer"]:
        assert repeat.asks(text), text
    for text in ["Last order was damaged, new request: 2 pallets", "our last shipment arrived late", "same day pickup", "with the usual paperwork"]:
        assert not repeat.asks(text), text


def test_only_the_same_senders_latest_priced_request_and_booked_first():
    sessions = [{"id": 1, "customer": "anna@meyer.example", "rfq": {**OLD, "destination": "JFK"}, "booking": {"booking_reference": "BK-1"}},
                {"id": 2, "customer": "anna@meyer.example", "rfq": OLD, "booking": None},
                {"id": 3, "customer": "other@x.example", "rfq": {**OLD, "destination": "LAX"}},
                {"id": 4, "customer": "anna@meyer.example", "rfq": {"origin": None, "destination": None}}]
    api = History(None, sessions)
    assert repeat.previous(api, "Anna <anna@MEYER.example>", 9)["id"] == 1  # the booked one is "our last order"
    assert repeat.previous(History(None, sessions[1:]), "anna@meyer.example", 9)["id"] == 2
    assert repeat.previous(api, "nobody@else.example", 9) is None


def test_a_bare_repeat_request_is_quoted_from_the_last_order(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (EMPTY, 0.0001))
    box = FixtureMailbox(tmp_path)
    api = History({"options": [OPTION], "chosen": OPTION, "why": "fastest"},
                  [{"id": 5, "customer": "anna@meyer.example", "rfq": OLD, "booking": {"booking_reference": "BK-5"}}])
    rfq_agent.handle_rfq(MAIL, box, api)
    assert "quote_sent" in api.events and len(box.sent) == 1
    rfq = api.data["extracted"]
    assert (rfq["origin"], rfq["destination"], rfq["ask"]) == ("FRA", "ORD", "fastest")
    assert rfq["pieces"] == OLD["pieces"] and rfq["volume_m3"] == 2.4
    assert rfq["excluded_airlines"] == ["Zephyr Steppe Cargo"] and rfq["ready_date"] == "2026-11-25"  # new date kept
    assert any(t.startswith("Repeat of session #5") for t in api.texts)


def test_what_the_new_mail_says_wins():
    rfq = {"origin": None, "destination": "LAX", "ask": "cheapest", "volume_m3": None,
           "pieces": [{"count": 5, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 100}]}
    missing, taken = repeat.fill(rfq, ["origin", "dimensions or volume"], {"ask": "cheapest"}, OLD)
    assert rfq["destination"] == "LAX" and rfq["origin"] == "FRA" and rfq["ask"] == "cheapest"
    assert rfq["pieces"][0]["weight_kg"] == 100 and rfq["volume_m3"] is None  # an old volume never meets a new weight
    assert missing == ["dimensions or volume"] and "pieces/weight" not in taken  # → priced on the actual weight


def test_no_earlier_order_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (EMPTY, 0.0001))
    box, api = FixtureMailbox(tmp_path), History({"options": [OPTION], "chosen": OPTION}, [])
    rfq_agent.handle_rfq(MAIL, box, api)
    assert "quote_sent" not in api.events  # nothing to price: the usual ask / person path
    assert any("there is none from" in t for t in api.texts)


BOOKED = [{"id": 11, "customer": "anna@meyer.example", "rfq": {**OLD, "destination": "JFK"},
           "booking": {"booking_reference": "BK-12345", "rate_id": "R-aa1"}},
          {"id": 12, "customer": "anna@meyer.example", "rfq": OLD, "booking": {"booking_reference": "BK-67890"}},
          {"id": 13, "customer": "other@x.example", "rfq": {**OLD, "destination": "LAX"}, "booking": {"booking_reference": "BK-55555"}},
          {"id": 14, "customer": "anna@meyer.example", "rfq": OLD, "booking": None, "quote": {"rate_id": "R-open"}}]
THREE = {**EMPTY, "pieces": [{"count": 3, "length": None, "width": None, "height": None, "weight": None, "weight_is_total": False}]}


def _run(tmp_path, monkeypatch, body):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (THREE, 0.0001))
    box = FixtureMailbox(tmp_path)
    api = History({"options": [OPTION], "chosen": OPTION, "why": "fastest"}, BOOKED)
    rfq_agent.handle_rfq({**MAIL, "body": body}, box, api)
    return box, api


def test_named_booking_is_that_booking_with_the_new_count(tmp_path, monkeypatch):
    assert repeat.reference("Same as booking BK-12345, just three pallets this time") == "BK-12345"
    box, api = _run(tmp_path, monkeypatch, "Hi, same as booking BK-12345, just three pallets this time. Anna")
    rfq = api.data["extracted"]
    assert rfq["destination"] == "JFK"  # the named booking, not the latest one (#2 → ORD)
    assert rfq["pieces"] == [{**OLD["pieces"][0], "count": 3}] and rfq["volume_m3"] == 2.4
    assert len(box.sent) == 1


def test_rate_id_reference_works_too(tmp_path, monkeypatch):
    box, api = _run(tmp_path, monkeypatch, "Please repeat R-aa1 for next week")
    assert api.data["extracted"]["destination"] == "JFK"


def test_unknown_foreign_or_unbooked_reference_is_never_guessed(tmp_path, monkeypatch):
    for body, why in [("same as booking BK-99999 please", "no session"), ("same as booking BK-55555 please", "another customer"),
                      ("same as R-open please", "not booked")]:
        box, api = _run(tmp_path, monkeypatch, body)
        assert box.sent == [] and "quote_sent" not in api.events and "needs_human" in api.events, body
        assert any(why in t for t in api.texts), (body, api.texts)
