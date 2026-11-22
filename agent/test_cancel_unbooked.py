"""Session 183: the customer said yes, then cancelled 18 s later. BOOK_GRACE_S held the booking, but the cancel went to
a person because read_intent didn't say decline. In stage quoted with no booking, a clear cancel gets the fixed
"nothing was booked, nothing to cancel" reply in the mail's language and the session closes (CANCEL_UNBOOKED)."""
import pytest

import booking_agent
from inbox import FixtureMailbox

QUOTE = {"source": "portal", "carrier": "Gannet Airways", "rate_id": "R-GN1", "currency": "EUR", "total": 2000.0,
         "transit_days": 2}
SESSION = {"id": 183, "customer": "buyer@acme.example", "thread_id": 7, "stage": "quoted", "llm_cost_usd": 0.0001,
           "rfq": {"origin": "FRA", "destination": "JFK", "language": "en", "contact_name": "Mia Lang",
                   "pieces": [{"count": 2, "weight_kg": 150}]},
           "quote": QUOTE, "bids": []}


class Api:
    def __init__(self, session=SESSION):
        self.state = {**session, "rfq": dict(session["rfq"])}
        self.updates, self.events, self.booked = [], [], []

    def session(self, session_id):
        return self.state

    def price(self, rfq, bids=None, fallback=False):
        return {"options": [QUOTE], "chosen": QUOTE}

    def update(self, session_id, **fields):
        self.updates.append(fields)
        self.state.update(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append((kind, text))

    def events_of(self, kind):
        return [text for k, text in self.events if k == kind]

    def book(self, session_id, rate_id):
        self.booked.append(rate_id)
        return {"booking_reference": "BK-1", "airline": "Gannet Airways", "rate_id": rate_id}


@pytest.fixture
def intent(monkeypatch):
    said = {"intent": "question", "topic": "other"}  # session 183: read_intent did NOT return decline
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a, **k: (said, 0.0))
    return said


def reply(body, tmp_path, session=SESSION, sender="buyer@acme.example"):
    api, box = Api(session), FixtureMailbox(tmp_path)
    booking_agent.handle_customer_reply({"id": 9, "thread_id": 7, "from": sender, "subject": "Re: quote", "body": body},
                                        box, api, dict(api.state))
    return api, box


@pytest.mark.parametrize("body", [
    "Sorry, ignore my yes, please cancel the booking.",  # a yes word and a cancel: read_intent asks the model
    "Please cancel, the order is off. Sorry for the yes earlier.",
    "Yes was too quick, please cancel the booking.",
    "Actually, please cancel: we will not book it after all, sorry.",  # read_intent's own decline
])
def test_session_183_a_cancel_after_a_held_yes_gets_nothing_was_booked(tmp_path, intent, body):
    api, box = reply(body, tmp_path)
    [sent] = box.sent
    assert "haven't booked anything" in sent["body"] and "nothing to cancel" in sent["body"]
    assert "EUR" not in sent["body"] and api.booked == []
    assert api.state["stage"] == "done" and api.state["outcome"] == "lost" and api.state["needs_human"] is False
    assert not any(k == "needs_human" for k, _ in api.events)


@pytest.mark.parametrize("body, start", [
    ("Bitte stornieren Sie den Auftrag, wir brauchen es doch nicht.", "Hallo"),
    ("Merci d'annuler, le client a retiré la commande.", "Bonjour"),
    ("Por favor, cancelen el pedido, ya no lo necesitamos.", "Hola"),
    ("Lütfen iptal edin, siparişi geri çektik. Storno lütfen.", "Merhaba"),
])
def test_the_reply_speaks_the_mail_language(tmp_path, intent, body, start):
    api, box = reply(body, tmp_path)
    assert box.sent[0]["body"].startswith(start) and api.state["stage"] == "done"


@pytest.mark.parametrize("body", [
    "What is your cancellation policy if we book now?",
    "No need to cancel, we just wanted to check the transit.",
    "Can we still cancel after booking if the buyer withdraws?",
    "Please cancel the second pallet, it is 1 pallet of 150 kg now.",  # a change: re-quoted
])
def test_no_cancel_is_never_closed_by_this_path(body):
    assert not booking_agent._cancels_unbooked({"from": "buyer@acme.example", "body": body}, SESSION)


def test_a_cancel_from_outside_the_company_is_never_closed_by_this_path():
    mail = {"from": "someone@other-firm.example", "body": "Sorry, ignore my yes, please cancel the booking."}
    assert booking_agent._cancels_unbooked({**mail, "from": "anna@acme.example"}, SESSION)
    assert not booking_agent._cancels_unbooked(mail, SESSION)


def test_a_booked_session_keeps_the_booked_cancel_path(tmp_path, intent):
    booked = {**SESSION, "stage": "booked", "booking": {"booking_reference": "BK-9", "airline": "Gannet Airways"}}
    api, box = reply("Please cancel the booking.", tmp_path, booked)
    assert not any("nothing to cancel" in m["body"] for m in box.sent)


def test_off_is_read_intent_as_before(tmp_path, intent, monkeypatch):
    monkeypatch.setattr(booking_agent, "CANCEL_UNBOOKED", False)
    api, box = reply("Sorry, ignore my yes, please cancel the booking.", tmp_path)  # session 183: a person, as before
    assert api.state.get("stage") != "done" and any(k == "needs_human" for k, _ in api.events)
