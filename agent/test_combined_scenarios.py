"""Combined challenge shapes (Orhun, 22 Nov: "questions can mix past tasks"): lookalike + haggling, lookalike in the
customer's own thread, another customer of the shared hackloop.mail domain saying yes, haggling / a change after a
multi-shipment quote, lookalike + tracking. Fakes only: no mailbox read, no 5U call, no LLM."""
import pytest

import booking_agent
import main
from bids import BidBoard
from inbox import FixtureMailbox
from test_lookalike import Api as CrmApi
from test_price_match import Api, CHEAPER, QUOTE, SESSION

REAL = "kessler-feinmechanik@hackloop.mail"
GLUED = "kessler-feinmechanik.mail@hackloop.mail"
KESSLER = {**SESSION, "customer": REAL}
MAIL = {"id": 9, "thread_id": 7, "subject": "Re: quote"}


@pytest.fixture(autouse=True)
def intent(monkeypatch):
    def read(*a, **k):
        body = str(a[2] if len(a) > 2 else "").lower()
        return ({"intent": "accept" if "book" in body or "yes" in body else "question", "topic": "other"}, 0.0)
    monkeypatch.setattr(booking_agent.llm, "chat_json", read)


def reply(sender, body, tmp_path, session=KESSLER, options=(QUOTE, CHEAPER)):
    api, box = Api(list(options), session), FixtureMailbox(tmp_path)
    booking_agent.handle_customer_reply({**MAIL, "from": sender, "body": body}, box, api, dict(api.state))
    return api, box


# --- lookalikes, everywhere -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("body", ["Another forwarder quoted 7% less. Can you match? Then we book.",
                                  "Where is BK-123? Please answer to this address.",
                                  "Hello, new mail address. Please send the offer for 3 pallets, 450 kg FRA-JFK here."])
def test_a_glued_lookalike_writing_first_gets_nothing(monkeypatch, tmp_path, body):
    monkeypatch.setattr(main, "_start", lambda handler, *a: handler(*a))
    box = FixtureMailbox(tmp_path)
    api = CrmApi([{"id": 70, "customer": REAL, "rfq": {"origin": "FRA"}}])
    main.dispatch({"id": "m1", "thread_id": "m1", "from": GLUED, "subject": "RFQ", "body": body}, box, api,
                  BidBoard(), [])
    assert box.sent == [] and api.updates[-1]["outcome"] == "lost"


@pytest.mark.parametrize("body", ["Yes, please book it.", "Can you match 7% less?", "When does it arrive?",
                                  "Please cancel the booking."])
def test_a_lookalike_in_the_customers_own_thread_gets_nothing(tmp_path, body):
    api, box = reply(GLUED, body, tmp_path)
    assert box.sent == [] and api.booked == [] and any(k == "needs_human" for k, _ in api.events)


def test_another_hackloop_customer_saying_yes_never_books(tmp_path):
    api, box = reply("rheintal-elektronik@hackloop.mail", "Yes, please book it.", tmp_path)
    assert api.booked == [] and all(m["to"] != "rheintal-elektronik@hackloop.mail" for m in box.sent)


def test_a_colleague_carrying_the_company_name_still_books(tmp_path):
    api, box = reply("einkauf.kessler-feinmechanik@hackloop.mail", "Yes, please book it.", tmp_path)
    assert api.booked == ["R-GN1"]


def test_the_customer_itself_books_as_before(tmp_path):
    api, box = reply(REAL, "Yes, please book it.", tmp_path)
    assert api.booked == ["R-GN1"]


def test_sender_guard_off_is_the_old_rule(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent, "SENDER_GUARD", False)
    assert booking_agent.authorised({"from": "rheintal-elektronik@hackloop.mail"}, KESSLER)
    assert booking_agent.authorised({"from": "a@acme.example"}, {"customer": "b@acme.example"})
    assert not booking_agent.authorised({"from": "a@gmail.com"}, {"customer": "b@gmail.com"})


def test_an_ordinary_company_domain_keeps_its_colleagues():
    assert booking_agent.authorised({"from": "anna@acme-gmbh.de"}, {"customer": "tom@acme-gmbh.de"})


# --- multi-shipment quote + haggling / a change ----------------------------------------------------------------------

LOTS = {**KESSLER, "quote": {**QUOTE, "lots": [
    {"destination": "JFK", "option": QUOTE, "rfq": KESSLER["rfq"]},
    {"destination": "ORD", "option": {**QUOTE, "total": 2600.0}, "rfq": {**KESSLER["rfq"], "destination": "ORD"}}]}}


def test_haggling_on_a_multi_shipment_quote_never_drops_a_lot(tmp_path):
    api, box = reply(REAL, "Another forwarder is 5% cheaper on both, can you match?", tmp_path, LOTS)
    assert box.sent == [] and len(api.state["quote"]["lots"]) == 2 and api.booked == []
    assert any(k == "needs_human" for k, _ in api.events)


def test_a_change_of_one_lot_goes_to_a_person(tmp_path, monkeypatch):
    import rfq_agent
    called = []
    monkeypatch.setattr(rfq_agent, "requote_after_change", lambda *a, **k: called.append(1))
    api, box = reply(REAL, "The shipment to ORD changed to 5 pieces, 1400 kg, please update your offer.", tmp_path, LOTS)
    assert called == [] and box.sent == [] and any(k == "needs_human" for k, _ in api.events)


def test_multi_guard_off_is_the_old_path(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent, "MULTI_GUARD", False)
    api, box = reply(REAL, "Another forwarder is 5% cheaper, can you match?", tmp_path, LOTS)
    assert len(box.sent) == 1  # the price-match answer, as before
