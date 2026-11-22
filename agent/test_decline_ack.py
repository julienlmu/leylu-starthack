"""Session 184: a sea FCL request DEHAM → AEJEA was declined (LANE_DECLINE). The customer answered "Understood, thanks
for letting me know" and a person got it: THANKS only counted after a booking. After any decline of ours, a thanks or
"understood" with nothing new gets no reply and the session stays closed (DECLINE_ACK)."""
import pytest

import booking_agent
from inbox import FixtureMailbox

DECLINED = {"id": 184, "customer": "buyer@acme.example", "thread_id": 7, "stage": "done", "outcome": "lost",
            "needs_human": False, "llm_cost_usd": 0.0001, "quote": None, "booking": None, "bids": [],
            "rfq": {"origin": "HAM", "destination": "DXB", "language": "en", "contact_name": "Mia Lang"}}


class Api:
    def __init__(self, session):
        self.state = dict(session)
        self.updates, self.events = [], []

    def session(self, session_id):
        return self.state

    def update(self, session_id, **fields):
        self.updates.append(fields)
        self.state.update(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append((kind, text))


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("no LLM call for an acknowledgment")
    monkeypatch.setattr(booking_agent.llm, "chat_json", refuse)


def reply(body, tmp_path, session=DECLINED):
    api, box = Api(session), FixtureMailbox(tmp_path)
    booking_agent.handle_customer_reply({"id": 9, "thread_id": 7, "from": "buyer@acme.example", "subject": "Re: RFQ",
                                         "body": body}, box, api, dict(api.state))
    return api, box


def closed_silently(api, box):
    return box.sent == [] and api.state["stage"] == "done" and api.state["needs_human"] is False \
        and not any(kind == "needs_human" for kind, _ in api.events)


@pytest.mark.parametrize("body", [
    "Understood, thanks for letting me know",  # session 184
    "Understood, thanks for letting me know.\n\nBest regards,\nMia Lang\nAcme GmbH | +49 89 1234 567",
    "Ok, no problem. Thanks anyway!",
    "Noted, thank you.",
    "Too bad. Thanks for the quick answer.",
    "Alles klar, danke für die Info.",
    "Verstanden, schade. Viele Grüße",
    "Compris, merci quand même.",
    "Entendido, gracias por avisar.",
    "Capito, grazie lo stesso.",
    "Begrepen, bedankt.",
    "Entendido, obrigada.",
    "Anladım, bilgi için teşekkürler.",
    "Tamam, sorun değil.",
    "了解しました。ありがとうございます。",
    "알겠습니다. 감사합니다.",
    "明白了，谢谢。",
    "Понятно, спасибо.",
    "Rozumiem, dziękuję.",
    "فهمت، شكرا",
])
def test_session_184_a_thanks_after_a_decline_gets_no_reply(tmp_path, body):
    api, box = reply(body, tmp_path)
    assert closed_silently(api, box)


@pytest.mark.parametrize("body", [
    "Understood. Could you quote it by air from FRA instead?",
    "Ok thanks, then please quote 2 pallets, 400 kg MUC to JFK.",
    "Understood, thanks. We also have another shipment to Dubai, can you help?",
    "Ok, then please book the air option after all.",
    "Schade. Können Sie uns stattdessen ein Angebot ab München schicken?",
    "Anladım ama başka bir teklif gönderebilir misiniz?",
    "Thanks, but please change the destination to Doha.",
])
def test_anything_new_still_reaches_a_person(tmp_path, monkeypatch, body):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a, **k: ({"intent": "question", "topic": "other"}, 0.0))
    api, box = reply(body, tmp_path)
    assert not closed_silently(api, box)


@pytest.mark.parametrize("session", [
    {**DECLINED, "stage": "booked", "outcome": "won", "booking": {"booking_reference": "BK-1"}},
    {**DECLINED, "stage": "done", "outcome": "cancelled", "booking": {"booking_reference": "BK-1", "cancelled": True}},
    {**DECLINED, "stage": "pricing", "outcome": "open"},
])
def test_only_a_closed_lost_session_with_nothing_booked(session):
    assert not booking_agent._acknowledges_decline(session, "Understood, thanks for letting me know")


def test_off_is_a_person_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent, "DECLINE_ACK", False)
    api, box = reply("Understood, thanks for letting me know", tmp_path)
    assert any(kind == "needs_human" for kind, _ in api.events)
