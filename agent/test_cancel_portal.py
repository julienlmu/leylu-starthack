"""CANCEL_PORTAL: a portal booking is cancelled with the portal's DELETE (backend /api/cancel); the customer hears
"cancelled" only on its 2xx. Any failure, or an email booking, → the airline is asked by email (CANCEL_AUTO). Fakes only."""
import booking_agent
from inbox import FixtureMailbox
from test_booking_tracking import REPLY, SESSION, FakeApi

CANCEL = {**REPLY, "body": "Sorry, our buyer withdrew the order. Please cancel the booking BK-UNAGWT8G."}
PORTAL = {**SESSION, "stage": "booked", "booking": {"booking_reference": "BK-UNAGWT8G", "status": "confirmed",
                                                    "airline": "Wayzata Air Cargo", "rate_id": "R-1"}}


class CancelApi(FakeApi):
    def __init__(self, sessions, ok=True):
        super().__init__(sessions)
        self.ok, self.cancels = ok, []

    def cancel(self, session_id):
        self.cancels.append(session_id)
        if not self.ok:
            raise RuntimeError("502 portal cancellation 404: unknown booking")
        return {**self.sessions[session_id]["booking"], "status": "cancelled", "cancel_requested": True}


def test_a_portal_booking_is_cancelled_on_the_portal_and_the_customer_told(tmp_path):
    box, api = FixtureMailbox(tmp_path), CancelApi([PORTAL])
    booking_agent.handle_customer_reply(CANCEL, box, api, api.session(17))
    assert api.cancels == [17] and len(box.sent) == 1  # the customer only: no mail to the airline
    assert "BK-UNAGWT8G" in box.sent[0]["body"] and "is cancelled" in box.sent[0]["body"]
    assert any(u.get("outcome") == "cancelled" and u["booking"]["status"] == "cancelled" for u in api.updates)
    booking_agent.handle_customer_reply({**CANCEL, "body": "Thanks, please let me know once the airline confirms the "
                                                           "cancellation."}, box, api, api.session(17))
    assert len(box.sent) == 1 and api.cancels == [17]  # one ack per booking: no second mail, no second DELETE


def test_a_failed_portal_cancellation_asks_the_airline_by_email_and_never_says_cancelled(tmp_path):
    box, api = FixtureMailbox(tmp_path), CancelApi([PORTAL], ok=False)
    booking_agent.handle_customer_reply(CANCEL, box, api, api.session(17))
    assert api.cancels == [17]
    to_airline = [m for m in box.sent if "wayzata" in (m.get("to") or "").lower()]
    to_customer = [m for m in box.sent if m not in to_airline]
    assert len(to_airline) == 1 and "please cancel booking BK-UNAGWT8G" in to_airline[0]["body"]
    assert len(to_customer) == 1 and "is cancelled" not in to_customer[0]["body"]


def test_an_email_booking_is_never_cancelled_on_the_portal(tmp_path):
    email = {**PORTAL, "booking": {**PORTAL["booking"], "pending_email": "wayzata-air-cargo@hackloop.mail"}}
    box, api = FixtureMailbox(tmp_path), CancelApi([email])
    booking_agent.handle_customer_reply(CANCEL, box, api, api.session(17))
    assert api.cancels == [] and any("please cancel booking" in m["body"] for m in box.sent)


def test_switch_off_asks_the_airline_by_email(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent, "CANCEL_PORTAL", False)
    box, api = FixtureMailbox(tmp_path), CancelApi([PORTAL])
    booking_agent.handle_customer_reply(CANCEL, box, api, api.session(17))
    assert api.cancels == []
