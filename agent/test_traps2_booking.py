"""Booking authorisation and confirmation traps (4, 12, 13, 14, 21): never book without a clear yes from an
authorised person, never tell a customer something is confirmed when it isn't. Fakes only, nothing is sent."""

import booking_agent
from booking_agent import handle_booking_confirmed, handle_customer_reply
from inbox import FixtureMailbox
from test_booking_tracking import BOOKING, REPLY, SESSION, FakeApi

AIRLINE = "meridian-freightways@hackloop.mail"
DG = {**SESSION, "rfq": {**SESSION["rfq"], "dangerous_goods": True}}
PAPERS = {**REPLY, "body": "Hi Lena, please find attached the shipper's declaration and the safety data sheet.",
          "attachments": [{"id": 1, "filename": "DGD.pdf"}]}


class Api(FakeApi):
    """FakeApi plus sessions() (the email-booking lookup)."""

    def __init__(self, sessions=()):
        super().__init__(sessions)
        self.all, self.texts = self.sessions, []
        self.sessions = lambda: list(self.all.values())

    def session(self, session_id):
        return self.all[session_id]

    def find(self, thread_id=None, reference=None):
        return next((s for s in self.all.values() if reference and
                     reference == (s.get("booking") or {}).get("booking_reference")), None)

    def update(self, session_id, **fields):
        self.updates.append(fields)
        self.all[session_id].update(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        super().event(session_id, kind, text, data, cost)
        self.texts.append((session_id, kind, text))


# 4: DG papers alone never book --------------------------------------------------------------------------------------

def test_dg_papers_without_a_yes_are_thanked_and_the_go_ahead_asked(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "other"}, 0.00003))
    box, api = FixtureMailbox(tmp_path), Api([DG])
    handle_customer_reply(PAPERS, box, api, DG)
    assert api.booked == [] and api.all[17]["stage"] == "quoted"
    [sent] = box.sent
    assert "until you confirm" in sent["body"] and "as soon as" not in sent["body"]


def test_dg_papers_with_a_clear_yes_book(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "other"}, 0.00003))
    box, api = FixtureMailbox(tmp_path), Api([DG])
    handle_customer_reply({**PAPERS, "body": PAPERS["body"] + " Please go ahead and book."}, box, api, DG)
    assert api.booked == ["R-1"]


def test_the_dg_quote_never_promises_to_book_on_the_papers_alone():
    from templates import docs_ack_text
    text = docs_ack_text(DG["rfq"], DG["quote"])
    assert "as soon as" not in text and "confirm" in text


# 12: a confirmation only from the airline we booked with, only for a pending booking ---------------------------------

def _portal_booked():
    return {**SESSION, "stage": "booked", "quote": {**SESSION["quote"], "carrier": "Meridian Freightways"},
            "booking": {**BOOKING, "airline": "Meridian Freightways"}}


def _confirmation(sender, ref="BK-1A2B3C4D", **extra):
    return {"id": 900, "thread_id": 900, "from": sender, "subject": f"Booking {ref} confirmed",
            "body": f"Booking {ref} confirmed.", "attachments": [], **extra}


def test_a_confirmation_from_the_booked_airline_is_recorded(tmp_path):
    box, api = FixtureMailbox(tmp_path), Api([_portal_booked()])
    assert handle_booking_confirmed(_confirmation(f"Meridian Freightways <{AIRLINE.upper()}>"), box, api)
    assert api.all[17]["booking"]["status"] == "confirmed" and box.sent[0]["to"] == "buyer@customer.example"


def test_a_fake_confirmation_from_anyone_else_is_ignored_with_a_note(tmp_path):
    for sender in ("buyer@customer.example", "meridian-freightways@hackl00p.mail", "polaris-air-logistics@hackloop.mail"):
        box, api = FixtureMailbox(tmp_path / sender), Api([_portal_booked()])
        assert handle_booking_confirmed(_confirmation(sender), box, api)
        assert api.all[17]["booking"]["status"] == "booked" and box.sent == [], sender
        assert any("ignored" in t for _, _, t in api.texts), sender


def test_a_second_confirmation_of_a_confirmed_booking_mails_nobody(tmp_path):
    session = _portal_booked()
    session["booking"]["status"] = "confirmed"
    box, api = FixtureMailbox(tmp_path), Api([session])
    assert handle_booking_confirmed(_confirmation(AIRLINE), box, api)
    assert box.sent == []


def test_a_fake_confirmation_never_completes_an_email_booking(tmp_path):
    pending = {**SESSION, "stage": "booked", "booking": {"pending_email": AIRLINE, "airline": "Meridian Freightways"}}
    box, api = FixtureMailbox(tmp_path), Api([pending])
    assert handle_booking_confirmed(_confirmation("ops@meridian-freightways.example", "BK-ABCD1234"), box, api)
    assert not api.all[17]["booking"].get("booking_reference") and box.sent == []


# 13: two email bookings pending with the same airline -----------------------------------------------------------------

def _two_pending():
    return [{**SESSION, "id": i, "thread_id": 100 + i, "stage": "booked",
             "booking": {"pending_email": AIRLINE, "airline": "Meridian Freightways", "team_reference": f"S-{i}",
                         "request_thread_id": 500 + i}} for i in (17, 18)]


def test_two_pending_email_bookings_an_unmatched_confirmation_goes_to_a_person(tmp_path):
    box, api = FixtureMailbox(tmp_path), Api(_two_pending())
    assert handle_booking_confirmed(_confirmation(AIRLINE, "BK-ABCD1234"), box, api)
    assert not any((s["booking"].get("booking_reference")) for s in api.all.values()) and box.sent == []
    assert "needs_human" in api.events


def test_two_pending_email_bookings_matched_by_our_reference_or_the_thread(tmp_path):
    box, api = FixtureMailbox(tmp_path), Api(_two_pending())
    by_ref = _confirmation(AIRLINE, "BK-ABCD1234")
    by_ref["body"] += " Your reference: S-17."
    handle_booking_confirmed(by_ref, box, api)
    assert api.all[17]["booking"]["booking_reference"] == "BK-ABCD1234" and not api.all[18]["booking"].get("booking_reference")
    box2, api2 = FixtureMailbox(tmp_path / "2"), Api(_two_pending())
    handle_booking_confirmed(_confirmation(AIRLINE, "BK-ABCD1234", thread_id=517), box2, api2)
    assert api2.all[17]["booking"]["booking_reference"] == "BK-ABCD1234"
    assert not api2.all[18]["booking"].get("booking_reference")


def test_the_booking_request_thread_is_stored(tmp_path):
    from test_booking_tracking import NoPortal
    session = {**SESSION, "quote": {**SESSION["quote"], "carrier": "Meridian Freightways", "rate_id": None}}
    box, api = FixtureMailbox(tmp_path), NoPortal([session])
    handle_customer_reply(REPLY, box, api, session)
    assert api.sessions[17]["booking"]["request_thread_id"] == box.sent[0]["thread_id"]


# 14: a yes from another person in the thread --------------------------------------------------------------------------

def test_a_yes_from_a_stranger_does_not_book_and_asks_the_contact(tmp_path):
    box, api = FixtureMailbox(tmp_path), Api([SESSION])
    handle_customer_reply({**REPLY, "from": "someone@gmail.com"}, box, api, SESSION)
    assert api.booked == [] and api.all[17]["stage"] == "quoted"
    [sent] = box.sent
    assert sent["to"] == "buyer@customer.example" and "BK-" not in sent["body"]


def test_a_yes_from_the_contact_or_a_colleague_books(tmp_path):
    for sender in ("Bob Buyer <BUYER@customer.example>", "boss@customer.example"):
        box, api = FixtureMailbox(tmp_path / sender), Api([SESSION])
        handle_customer_reply({**REPLY, "from": sender}, box, api, SESSION)
        assert api.booked == ["R-1"], sender


def test_a_free_mail_domain_is_no_company(tmp_path):
    session = {**SESSION, "customer": "anna@gmail.com"}
    box, api = FixtureMailbox(tmp_path), Api([session])
    handle_customer_reply({**REPLY, "from": "mallory@gmail.com"}, box, api, session)
    assert api.booked == []


# 21: cancel after booking -----------------------------------------------------------------------------------------------

def test_a_cancellation_after_booking_is_acknowledged_and_flagged(tmp_path):
    booked = {**SESSION, "stage": "booked", "booking": BOOKING}
    for body in ("Please cancel the booking, the order was withdrawn.", "We need to cancel this shipment.",
                 "Bitte stornieren Sie die Buchung."):
        box, api = FixtureMailbox(tmp_path / body[:8]), Api([booked])
        handle_customer_reply({**REPLY, "body": body}, box, api, booked)
        [sent] = box.sent
        assert "BK-1A2B3C4D" in sent["body"] and "EUR" not in sent["body"], body
        assert not any(w in sent["body"].lower() for w in ("has been cancelled", "is cancelled", "storniert.")), body
        assert api.all[17]["needs_human"] is True and "needs_human" in api.events, body
        assert any("cancel" in u["text"].lower() for u in api.all[17]["status_updates"]), body


def test_a_cancellation_policy_question_is_no_cancellation(tmp_path):
    booked = {**SESSION, "stage": "booked", "booking": BOOKING}
    box, api = FixtureMailbox(tmp_path), Api([booked])
    handle_customer_reply({**REPLY, "body": "What is your cancellation policy?"}, box, api, booked)
    assert box.sent == [] and "needs_human" in api.events
