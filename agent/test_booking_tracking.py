import booking_agent
from booking_agent import handle_booking_confirmed, handle_customer_reply, latest_text, read_intent
from inbox import FixtureMailbox
from router import route
from tracking_agent import handle_tracking

BOOKING = {"booking_reference": "BK-1A2B3C4D", "team_reference": "17", "rate_id": "R-1", "airline": "SkyAir",
           "airline_code": "SK", "price": "1856.00", "currency": "EUR", "status": "booked"}
SESSION = {"id": 17, "customer": "buyer@customer.example", "thread_id": 101, "stage": "quoted", "llm_cost_usd": 0.0001,
           "rfq": {"origin": "MUC", "destination": "JFK"},
           "quote": {"carrier": "SkyAir", "rate_id": "R-1", "currency": "EUR", "total": 1856.0, "transit_days": 2}}
REPLY = {"id": 105, "thread_id": 101, "from": "buyer@customer.example", "subject": "Re: RFQ MUC-JFK",
         "body": "Yes please, go ahead.\n\nOn Sat, team wrote:\n> Just reply to this email and we'll book it"}


class FakeApi:
    def __init__(self, sessions=()):
        self.sessions = {s["id"]: dict(s) for s in sessions}
        self.updates, self.events, self.booked, self.lookups = [], [], [], []

    def session(self, session_id):
        return self.sessions[session_id]

    def find(self, thread_id=None, reference=None):
        self.lookups.append(reference)
        return next((s for s in self.sessions.values()
                     if reference in (s.get("booking") or {}).get("booking_reference", "")), None)

    def update(self, session_id, **fields):
        self.updates.append(fields)
        self.sessions[session_id].update(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append(kind)

    def book(self, session_id, rate_id):
        self.booked.append(rate_id)
        return BOOKING


def test_latest_text_drops_our_quoted_mail():
    assert latest_text(REPLY["body"]).strip() == "Yes please, go ahead."


def test_read_intent_uses_rules_for_clear_answers_and_the_llm_otherwise(monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "question"}, 0.00003))
    assert read_intent(REPLY["body"]) == ("accept", 0.0)
    assert read_intent("No thanks, that's too expensive.") == ("decline", 0.0)
    assert read_intent("Looks ok, but can you do it cheaper?") == ("question", 0.00003)


def test_accepted_quote_is_booked_by_rate_id_and_confirmed_in_thread(tmp_path):
    box, api = FixtureMailbox(tmp_path), FakeApi([SESSION])
    handle_customer_reply(REPLY, box, api, SESSION)
    assert api.booked == ["R-1"]
    [sent] = box.sent
    assert sent["thread_id"] == 101 and "BK-1A2B3C4D" in sent["body"]
    assert api.sessions[17]["stage"] == "booked" and api.sessions[17]["outcome"] == "won"
    assert api.events == ["mail_in", "accepted", "booked"]


def test_airline_confirmation_updates_the_crm_and_informs_the_customer(tmp_path):
    box, api = FixtureMailbox(tmp_path), FakeApi([{**SESSION, "stage": "booked", "booking": BOOKING}])
    mail = {"id": 120, "thread_id": 120, "from": "ops@skyair.example", "subject": "Booking BK-1A2B3C4D confirmed",
            "body": "…", "attachments": []}
    assert route(mail, {"ops@skyair.example"}, known_thread=False) == "booking_confirmed"
    assert handle_booking_confirmed(mail, box, api)
    assert api.sessions[17]["booking"]["status"] == "confirmed"
    assert box.sent[0]["thread_id"] == 101  # told the customer in their own thread


def test_tracking_question_is_answered_from_the_crm(tmp_path):
    session = {**SESSION, "stage": "booked", "booking": {**BOOKING, "status": "confirmed"}}
    box, api = FixtureMailbox(tmp_path), FakeApi([session])
    mail = {"id": 130, "thread_id": 130, "from": "tracking@hackloop.mail",
            "subject": "Status BK-1A2B3C4D", "body": "Where is shipment BK-1A2B3C4D right now?"}
    handle_tracking(mail, box, api)
    [answer] = box.sent
    assert "BK-1A2B3C4D" in answer["body"] and "confirmed by the airline" in answer["body"]
    assert api.events == ["tracking_answer"]


def test_tracking_question_for_an_unknown_booking_asks_for_the_reference(tmp_path):
    box, api = FixtureMailbox(tmp_path), FakeApi()
    mail = {"id": 131, "thread_id": 131, "from": "tracking@hackloop.mail", "subject": "Status?",
            "body": "Where is BK-ZZZZZZZZ?"}
    handle_tracking(mail, box, api)
    assert "starts with BK-" in box.sent[0]["body"]
