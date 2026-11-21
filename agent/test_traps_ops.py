"""Trap probes 19 / 20 / 21 (ops traps): weak tracking identifiers, unsupported languages, manual reply vs fallback."""
from inbox import FixtureMailbox
from test_tracking_match import OTHER, QUESTION, SONNBERG
from test_booking_tracking import FakeApi
from tracking_agent import handle_tracking

SONNBERG_NAMED = {**SONNBERG, "rfq": {**SONNBERG["rfq"], "contact_name": "Anna Sonnberg"}}


def _track(body, subject="Shipment status", sender="tracking@hackloop.mail", tmp_path=None):
    box, api = FixtureMailbox(tmp_path), FakeApi([OTHER, SONNBERG_NAMED])
    handle_tracking({**QUESTION, "from": sender, "subject": subject, "body": body}, box, api)
    [answer] = box.sent
    return answer["body"]


def test_19_a_weak_identifier_alone_never_picks_a_shipment(tmp_path):
    for body in ["Hi, where is Anna's shipment? Thanks, Anna",  # first name only
                 "Status for Sonnberg please?",  # part of the company name
                 "Can you tell me where the Kaffee shipment is?",  # one word of the company
                 "Where is BK-50NM8E9G?",  # two typos in the booking reference
                 "Where is BK-5ONN8E8?",  # one typo + missing character, nothing else agrees
                 "Where is BK-50NN8E9G?"]:  # one typo, shared mail domain, no second signal
        answer = _track(body, tmp_path=tmp_path)
        assert "BK-50NN8E8G" not in answer and "BK-OTHER123" not in answer, (body, answer)


def test_19_a_second_signal_still_finds_it(tmp_path):
    answer = _track("Where is BK-50NN8E9G? It's the 1233 kg to JFK.", tmp_path=tmp_path)
    assert "BK-50NN8E8G" in answer


ACCEPTS = ["Igen, kérem, foglalják le.", "Rendben, elfogadjuk az ajánlatot.",  # Hungarian
           "네, 예약해 주세요.", "좋습니다. 진행해 주세요.",  # Korean
           "نعم، يرجى الحجز.", "موافق، احجزوا من فضلكم."]  # Arabic
DECLINES = ["Nem, köszönjük, túl drága.", "Sajnos elutasítjuk az ajánlatot.",
            "아니요, 너무 비싸요.", "죄송하지만 거절하겠습니다.",
            "لا، شكرا، السعر مرتفع جدا.", "نعتذر، نرفض العرض."]


def test_20_yes_and_no_in_hungarian_korean_arabic_are_read_by_rules(monkeypatch):
    import pytest
    from booking_agent import read_intent
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: pytest.fail(f"no LLM for a plain yes/no: {a[2]}"))
    for text in ACCEPTS:
        assert read_intent(text) == ("accept", 0.0), text
    for text in DECLINES:
        assert read_intent(text) == ("decline", 0.0), text


def test_20_hungarian_yes_books_once_and_the_mail_falls_back_to_english_without_a_translation(tmp_path, monkeypatch):
    import short_mail
    from booking_agent import handle_customer_reply
    from test_booking_tracking import REPLY, SESSION
    monkeypatch.setattr(short_mail, "CACHE", tmp_path / "langs.json")
    monkeypatch.setattr(short_mail, "_tried", set())
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))  # gateway down
    session = {**SESSION, "rfq": {**SESSION["rfq"], "language": "hu"}}
    box, api = FixtureMailbox(tmp_path), FakeApi([session])
    handle_customer_reply({**REPLY, "body": "Igen, kérem, foglalják le."}, box, api, session)
    assert api.booked == ["R-1"]
    [sent] = box.sent
    assert "BK-1A2B3C4D" in sent["body"]


def test_21_a_person_pausing_while_the_fallback_quote_is_written_stops_it(monkeypatch, tmp_path):
    # The UI pauses the session before a manual send; the fallback checks paused/quote again right before its send.
    import rfq_agent
    from test_fallback_races import Stateful, _setup
    from test_rfq_agent import MAIL, OPTION, BidBoard
    _setup(monkeypatch)
    api = Stateful({"options": [], "chosen": None, "why": ""})
    api.fallback_result = {"options": [OPTION], "chosen": OPTION, "why": "earlier bid"}
    gate = rfq_agent._fallback_gate

    def person_pauses_now(*a):
        api.state["paused"] = True
        return gate(*a)
    monkeypatch.setattr(rfq_agent, "_fallback_gate", person_pauses_now)
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert box.sent == [], "fallback quote went out after a person paused the session"


def test_20_a_question_or_a_mixed_reply_is_never_booked_by_rules(monkeypatch):
    from booking_agent import read_intent
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: ({"intent": "question"}, 0.0001))
    for text in ["Igen, de nem most, jövő héten?", "예약 전에 보험이 포함되어 있나요?", "نعم ولكن هل السعر يشمل التأمين؟"]:
        assert read_intent(text)[0] != "accept", text
