"""S115 LOOKALIKE: kessler-feinmechanik.mail@hackloop.mail (the customer's local part + ".mail") wrote "new mail address,
send the LIM offer here". It got a details question; it must get nothing at all (Orhun: lookalikes, no reply)."""
import pytest

import lookalike
import main
from bids import BidBoard
from inbox import FixtureMailbox
from test_lookalike import Api

REAL = "kessler-feinmechanik@hackloop.mail"
S115 = {"id": "m115", "thread_id": "m115", "from": "kessler-feinmechanik.mail@hackloop.mail",
        "to": "quotes@leylu.example", "subject": "LIM offer",
        "body": "Hello, this is our new mail address. Please send the LIM offer here. Regards, Kessler Feinmechanik"}


@pytest.mark.parametrize("sender, level", [
    ("kessler-feinmechanik.mail@hackloop.mail", "strong"),  # S115
    ("kessler-feinmechanik-mail@hackloop.mail", "strong"),
    ("kesslerfeinmechanikmail@hackloop.mail", "strong"),
    ("mail.kessler-feinmechanik@hackloop.mail", "strong"),
    ("kessler-feinmechanik.new@hackloop.mail", "strong"),
    ("kessler-feinmechanik2@hackloop.mail", "strong"),
    ("kessler-feinmechanik.mail@hackloop.co", "strong"),
    ("kessler-feinmechanik.mail@gmail.com", None),  # another provider: only with a red flag (imitated)
    ("einkauf.kessler-feinmechanik@hackloop.mail", None),  # may be a colleague: only with a red flag
    ("kessler-logistik@hackloop.mail", None),
    ("kessler@hackloop.mail", None),
])
def test_glued_word(sender, level):
    assert lookalike.strength(sender, REAL) == level


def test_s115_is_found_and_gets_no_reply(monkeypatch, tmp_path):
    assert lookalike.imitated(S115, [REAL]) == REAL
    monkeypatch.setattr(main, "_start", lambda handler, *a: handler(*a))
    box, api = FixtureMailbox(tmp_path), Api([{"id": 70, "customer": REAL, "rfq": {"origin": "FRA"}}])
    main.dispatch(S115, box, api, BidBoard(), [])
    assert box.sent == [] and api.updates[-1]["outcome"] == "lost" and api.updates[-1]["stage"] == "done"


@pytest.mark.parametrize("sender", ["einkauf.kessler-feinmechanik@hackloop.mail", "kessler-feinmechanik.mail@gmail.com",
                                    "kessler-feinmechanik@gmail.com"])
def test_a_weaker_glue_counts_with_a_red_flag(sender):
    assert lookalike.imitated({**S115, "from": sender}, [REAL]) == REAL
    assert lookalike.imitated({**S115, "from": sender, "body": "Please quote 2 pallets 300 kg FRA-JFK"}, [REAL]) is None


@pytest.mark.parametrize("body", ["this is our new mail address", "Please send the LIM offer here",
                                  "reply here please, our mailbox is down", "Das ist unsere neue Mailadresse"])
def test_new_red_flags(body):
    assert lookalike.RED_FLAG.search(body), body


@pytest.mark.parametrize("body", ["Please send us your quote for 300 kg FRA-JFK", "Delivery to our new address in Munich",
                                  "Here are the details: 3 pallets, 450 kg FRA-JFK", "New shipment: 2 pallets to JFK"])
def test_still_no_red_flag(body):
    assert not lookalike.RED_FLAG.search(body)


def test_an_unknown_sender_claiming_a_new_address_without_figures_gets_nothing(monkeypatch, tmp_path):
    mail = {**S115, "from": "k.feinmechanik@protonmail.com"}
    assert lookalike.imitated(mail, [REAL]) == lookalike.NEW_ADDRESS_CLAIM
    monkeypatch.setattr(main, "_start", lambda handler, *a: handler(*a))
    box, api = FixtureMailbox(tmp_path), Api([{"id": 70, "customer": REAL, "rfq": {"origin": "FRA"}}])
    main.dispatch(mail, box, api, BidBoard(), [])
    assert box.sent == [] and api.updates[-1] == {"outcome": "lost", "needs_human": True}


def test_a_new_customer_with_a_real_request_is_quoted_as_usual(monkeypatch, tmp_path):
    mail = {**S115, "from": "buyer@new-firm.example", "subject": "RFQ FRA-JFK",
            "body": "This is my new email address. Please quote 3 pallets, 450 kg, FRA to JFK, ready Monday."}
    assert lookalike.imitated(mail, [REAL]) is None
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))
    main.dispatch(mail, FixtureMailbox(tmp_path), Api([{"id": 70, "customer": REAL}]), BidBoard(), [])
    assert started and started[0] != "decline_lookalike"


def test_the_real_customer_announcing_nothing_is_never_flagged():
    assert lookalike.imitated({**S115, "from": REAL}, [REAL]) is None


@pytest.mark.parametrize("body, flagged", [
    ("New mail address. Please send the LIM offer here.", True),
    ("Our mailbox is down, please resend our quote to this address.", True),
    ("Unser Postfach ist ausgefallen, bitte schicken Sie das Angebot an diese Adresse.", True),
    ("Our mailbox is down, use this address", False),  # no earlier offer asked for: may be a real first contact
    ("This is our new mail address, please send the offer for 300 kg FRA-JFK here", False),  # a real request
])
def test_new_address_claim(body, flagged):
    mail = {**S115, "from": "someone@elsewhere.example", "body": body}
    assert (lookalike.imitated(mail, [REAL]) == lookalike.NEW_ADDRESS_CLAIM) is flagged, body
