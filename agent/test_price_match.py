"""R111 PRICE_MATCH: "looks good, but another forwarder quoted 7% less, can you match?". The lowest real all-in now
(priced again with the session's bids), never below it, one amount, the quote re-pointed so a yes books it."""
import re

import pytest

import booking_agent
import price_match
from inbox import FixtureMailbox

QUOTE = {"source": "portal", "carrier": "Gannet Airways", "rate_id": "R-GN1", "currency": "EUR", "total": 2000.0,
         "transit_days": 2}
CHEAPER = {"source": "carrier_bid", "carrier": "Borealis Freight Airways", "rate_id": None, "currency": "EUR",
           "total": 1900.0, "transit_days": 4}
SESSION = {"id": 111, "customer": "buyer@acme.example", "thread_id": 7, "stage": "quoted", "llm_cost_usd": 0.0001,
           "rfq": {"origin": "FRA", "destination": "JFK", "language": "en", "contact_name": "Mia Lang"},
           "quote": QUOTE, "bids": [{"carrier": "Borealis Freight Airways", "total": 1900.0, "currency": "EUR"}]}


class Api:
    def __init__(self, options, session=SESSION):
        self.options, self.state = options, {**session, "rfq": dict(session["rfq"])}
        self.updates, self.events, self.booked, self.priced = [], [], [], []

    def session(self, session_id):
        return self.state

    def price(self, rfq, bids=None, fallback=False):
        self.priced.append((rfq, bids))
        return {"options": self.options, "chosen": self.options[0] if self.options else None}

    def update(self, session_id, **fields):
        self.updates.append(fields)
        self.state.update(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append((kind, text))

    def book(self, session_id, rate_id):
        self.booked.append(rate_id)
        return {"booking_reference": "BK-1", "airline": self.state["quote"]["carrier"], "rate_id": rate_id}


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a, **k: ({"intent": "question", "topic": "other"}, 0.0))


def reply(text, options, tmp_path, session=SESSION):
    api, box = Api(options, session), FixtureMailbox(tmp_path)
    booking_agent.handle_customer_reply({"id": 9, "thread_id": 7, "from": "buyer@acme.example", "subject": "Re: quote",
                                         "body": text}, box, api, dict(api.state))
    return api, box


def amounts(body):
    return re.findall(r"EUR [\d,]+\.\d\d", body)


def test_r111_seven_percent_less_is_matched_by_the_cheaper_real_rate(tmp_path):
    # 7 % less than 2,000 = 1,860; our best real all-in is 1,900: can't match, best is 1,900
    api, box = reply("Looks good, but another forwarder quoted 7% less. Can you match?", [QUOTE, CHEAPER], tmp_path)
    body = box.sent[0]["body"]
    assert amounts(body) == ["EUR 1,900.00"] and "can't go as low as 7 % less" in body and "Borealis" in body
    assert api.state["quote"]["total"] == 1900.0 and api.state["quote"]["carrier"] == "Borealis Freight Airways"
    assert api.state["quote"]["price_match_from"] == 2000.0 and api.booked == []


def test_a_smaller_ask_is_met_with_our_best_all_in(tmp_path):
    api, box = reply("Can you do 3% less? Then we book.", [QUOTE, CHEAPER], tmp_path)  # 1,940 asked, 1,900 possible
    body = box.sent[0]["body"]
    assert amounts(body) == ["EUR 1,900.00"] and "I can offer it for EUR 1,900.00" in body and api.booked == []


def test_an_absolute_price_ask_never_gets_their_figure_written_back(tmp_path):
    api, box = reply("Another agent offered EUR 1,750. Can you beat that?", [QUOTE, CHEAPER], tmp_path)
    body = box.sent[0]["body"]
    assert amounts(body) == ["EUR 1,900.00"] and "1,750" not in body and "your target price" in body


def test_best_price_question_gets_the_lowest_all_in(tmp_path):
    api, box = reply("Is that your best price?", [QUOTE, CHEAPER], tmp_path)
    assert amounts(box.sent[0]["body"]) == ["EUR 1,900.00"] and "can't" not in box.sent[0]["body"]


def test_nothing_cheaper_holds_our_quote(tmp_path):
    api, box = reply("Another forwarder quoted 10% less, can you match?", [QUOTE], tmp_path)
    body = box.sent[0]["body"]
    assert amounts(body) == ["EUR 2,000.00"] and "already the best price" in body
    assert api.state["quote"] == QUOTE  # not re-pointed


def test_never_a_higher_price_when_the_rates_went_up(tmp_path):
    dearer = {**QUOTE, "rate_id": "R-GN2", "total": 2150.0}
    api, box = reply("Can you do better?", [dearer], tmp_path)
    assert amounts(box.sent[0]["body"]) == ["EUR 2,000.00"] and api.state["quote"]["rate_id"] == "R-GN1"


def test_never_below_cost_even_when_they_ask_for_a_lot(tmp_path):
    api, box = reply("We need 40% less, otherwise no deal.", [QUOTE, CHEAPER], tmp_path)
    assert amounts(box.sent[0]["body"]) == ["EUR 1,900.00"]  # the cheapest real option, not 1,200


def test_repeated_haggling_holds_the_floor_and_then_goes_to_a_person(tmp_path):
    api = Api([QUOTE, CHEAPER])
    box = FixtureMailbox(tmp_path)
    mail = {"id": 9, "thread_id": 7, "from": "buyer@acme.example", "subject": "Re: quote"}
    booking_agent.handle_customer_reply({**mail, "body": "Can you match 7% less?"}, box, api, dict(api.state))
    booking_agent.handle_customer_reply({**mail, "body": "Come on, any discount at all?"}, box, api, dict(api.state))
    assert amounts(box.sent[1]["body"]) == ["EUR 1,900.00"] and "nothing has changed" in box.sent[1]["body"]
    booking_agent.handle_customer_reply({**mail, "body": "Still too expensive. Best price?"}, box, api, dict(api.state))
    booking_agent.handle_customer_reply({**mail, "body": "Final: can you do 5% less?"}, box, api, dict(api.state))
    assert len(box.sent) == 3 and any(k == "needs_human" for k, _ in api.events)


def test_a_yes_after_the_match_books_the_offered_option(tmp_path):
    api = Api([QUOTE, {**CHEAPER, "rate_id": "R-BX9", "source": "portal"}])
    box = FixtureMailbox(tmp_path)
    mail = {"id": 9, "thread_id": 7, "from": "buyer@acme.example", "subject": "Re: quote"}
    booking_agent.handle_customer_reply({**mail, "body": "Can you match 5% less?"}, box, api, dict(api.state))
    booking_agent.handle_customer_reply({**mail, "body": "Yes, book it."}, box, api, dict(api.state))
    assert api.booked == ["R-BX9"]


def test_german(tmp_path):
    session = {**SESSION, "rfq": {**SESSION["rfq"], "language": "de"}}
    api, box = reply("Ein Mitbewerber ist 5 % günstiger, geht da noch was?", [QUOTE, CHEAPER], tmp_path, session)
    body = box.sent[0]["body"]
    assert "mein bester Preis ist EUR 1,900.00" in body or "anbieten" in body
    assert amounts(body) == ["EUR 1,900.00"]


def test_no_fresh_price_goes_to_a_person_as_before(tmp_path):
    class Down(Api):
        def price(self, rfq, bids=None, fallback=False):
            raise ConnectionError("backend down")
    api, box = Down([QUOTE]), FixtureMailbox(tmp_path)
    booking_agent.handle_customer_reply({"id": 9, "thread_id": 7, "from": "buyer@acme.example", "subject": "Re",
                                         "body": "Can you match 7% less?"}, box, api, dict(api.state))
    assert box.sent == [] and api.booked == [] and any(k == "needs_human" for k, _ in api.events)


def test_switch_off_is_the_old_hand_over(tmp_path, monkeypatch):
    monkeypatch.setattr(price_match, "ON", False)
    api, box = reply("Can you match 7% less?", [QUOTE, CHEAPER], tmp_path)
    assert box.sent == [] and api.booked == [] and any(k == "needs_human" for k, _ in api.events)


def test_a_change_of_the_shipment_is_no_price_match(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(booking_agent, "_price_match", lambda *a: seen.append(1) or True)
    import rfq_agent
    monkeypatch.setattr(rfq_agent, "requote_after_change", lambda *a, **k: None)
    reply("The shipment changed to 5 pieces, 1317 kg, please update your offer.", [QUOTE], tmp_path)
    assert seen == []


@pytest.mark.parametrize("text, pct", [("7% less", 7.0), ("can you go 5 % lower", 5.0), ("10% cheaper", 10.0),
                                       ("discount of 3,5%", 3.5), ("um 4% günstiger", 4.0), ("lower by 6%", 6.0)])
def test_percent(text, pct):
    assert price_match.percent(text) == pct


@pytest.mark.parametrize("text, asks", [
    ("another forwarder quoted 7% less, can you match?", True), ("Is this your best price?", True),
    ("Can you do it cheaper?", True), ("Any room on the price?", True), ("Too expensive for us.", True),
    ("Geht es günstiger?", True), ("Yes please book it", False), ("When does it arrive?", False),
    ("Please include the pickup", False),
])
def test_asks(text, asks):
    assert price_match.asks(text) is asks


@pytest.mark.parametrize("text", ["OK, book it at EUR 1,950.", "We'd accept at 1,880 EUR.", "Our budget is EUR 1,800."])
def test_a_lower_counter_offer_is_answered_too_and_never_books(tmp_path, text):
    api, box = reply(text, [QUOTE, CHEAPER], tmp_path)
    assert api.booked == [] and amounts(box.sent[0]["body"]) == ["EUR 1,900.00"], text
