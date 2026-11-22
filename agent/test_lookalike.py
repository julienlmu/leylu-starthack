"""R108 LOOKALIKE: nordlicht.audio@ (dot) wrote as the customer nordlicht-audio@ (hyphen): "our mailbox is down,
confirm your price for BKK to this address". Never a price or session data to a lookalike address."""
import pytest

import lookalike
import main
import rfq_agent
from bids import BidBoard
from inbox import FixtureMailbox

REAL = "Jonas Berg <nordlicht-audio@nordlicht-audio.de>"
R108 = {"id": "m108", "thread_id": "m108", "from": "nordlicht.audio@nordlicht-audio.de", "to": "quotes@leylu.example",
        "subject": "Urgent: price confirmation BKK",
        "body": "Hi, our mailbox is down at the moment. Please confirm your price for BKK to this address. Thanks, Jonas"}


@pytest.mark.parametrize("sender, known, level", [
    ("nordlicht.audio@nordlicht-audio.de", "nordlicht-audio@nordlicht-audio.de", "strong"),  # R108: '.' vs '-'
    ("nordlichtaudio@nordlicht-audio.de", "nordlicht-audio@nordlicht-audio.de", "strong"),
    ("nordlicht-audio@nordlicht-audio.com", "nordlicht-audio@nordlicht-audio.de", "strong"),  # another ending
    ("nordlicht-audio@nordlichtaudio.de", "nordlicht-audio@nordlicht-audio.de", "strong"),
    ("nordlicht-audio@nordlicht-audi0.de", "nordlicht-audio@nordlicht-audio.de", "strong"),  # 0 for o
    ("anna@meyer-gmbh.de", "anna@meyer-gmbh.de", None),  # the same address
    ("ANNA@Meyer-GmbH.de", "anna@meyer-gmbh.de", None),  # case only: the same mailbox
    ("anna@meyr-gmbh.de", "anna@meyer-gmbh.de", "strong"),  # domain one letter off
    ("buyer@rnetalworks.example", "buyer@metalworks.example", "strong"),  # rn for m
    ("purchasing@acme.example", "purchasimg@acme.example", "weak"),  # one letter off at the same domain
    ("anna@meyer-gmbh.de", "anne@meyer-gmbh.de", None),  # short local parts: two colleagues
    ("tom@acme.example", "lisa@acme.example", None),
    ("info@other-company.de", "nordlicht-audio@nordlicht-audio.de", None),
    ("anna@gmail.com", "anna@gmx.com", None),
])
def test_strength(sender, known, level):
    assert lookalike.strength(sender, known) == level


def test_a_weak_lookalike_counts_only_with_a_red_flag():
    customers = ["purchasing@acme.example"]
    mail = {"from": "purchasimg@acme.example", "subject": "RFQ", "body": "3 pallets FRA-JFK, 450 kg, please quote"}
    assert lookalike.imitated(mail, customers) is None
    assert lookalike.imitated({**mail, "body": "Please send the quote to this address, our mailbox is down"},
                              customers) == "purchasing@acme.example"


@pytest.mark.parametrize("body", [
    "our mailbox is down, confirm your price for BKK to this address",
    "We changed our email, please use this new address from now on",
    "Please resend the quote here, our server has problems",
    "Unser Postfach ist gerade gestört, bitte an diese Adresse",
    "please confirm the booking and send our bank details",
])
def test_red_flags(body):
    assert lookalike.RED_FLAG.search(body), body


def test_r108_is_found_and_the_known_customer_is_never_a_lookalike():
    assert lookalike.imitated(R108, [REAL, "other@x.example"]) == "nordlicht-audio@nordlicht-audio.de"
    assert lookalike.imitated({**R108, "from": REAL}, [REAL]) is None
    # a sender that already has its own session is a customer of its own
    assert lookalike.imitated(R108, [REAL, "nordlicht.audio@nordlicht-audio.de"]) is None


def test_switch_off(monkeypatch):
    monkeypatch.setattr(lookalike, "ON", False)
    assert lookalike.imitated(R108, [REAL]) is None


class Api:
    def __init__(self, sessions):
        self.history, self.events, self.updates, self.created = sessions, [], [], []

    def find(self, thread_id):
        return None

    def sessions(self, stage=None):
        return self.history

    def create_session(self, customer, thread_id, received_at=None):
        self.created.append(customer)
        return 108

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append((kind, text))

    def update(self, session_id, **fields):
        self.updates.append(fields)


def test_r108_gets_the_fixed_decline_without_price_lane_or_the_real_address(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "_start", lambda handler, *a: handler(*a))
    box = FixtureMailbox(tmp_path)
    api = Api([{"id": 77, "customer": REAL, "rfq": {"origin": "FRA", "destination": "BKK"},
                "quote": {"total": 1830.0, "currency": "EUR", "carrier": "Gannet Airways"}}])
    main.dispatch(R108, box, api, BidBoard(), [])
    assert len(box.sent) == 1
    body = box.sent[0]["body"]
    for leak in ("EUR", "1830", "1,830", "BKK", "FRA", "Gannet", "nordlicht-audio@", "S-77"):
        assert leak not in body, leak
    assert "address we have on file" in body
    assert api.updates[-1]["outcome"] == "lost" and any("imitates" in t for _, t in api.events)


def test_a_tracking_question_from_a_lookalike_gets_no_status(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))
    monkeypatch.setattr(main, "route", lambda *a, **k: "tracking", raising=False)
    api = Api([{"id": 77, "customer": REAL, "booking": {"booking_reference": "BK-777"}}])
    main.dispatch({**R108, "body": "Where is BK-777? Mailbox down, answer to this address."}, FixtureMailbox(tmp_path),
                  api, BidBoard(), [])
    assert started == ["decline_lookalike"]


def test_a_normal_rfq_from_a_new_customer_goes_on_as_usual(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))
    api = Api([{"id": 77, "customer": REAL}])
    mail = {**R108, "from": "buyer@another-firm.example", "subject": "RFQ FRA-JFK",
            "body": "Please quote 3 pallets, 450 kg, FRA to JFK, ready Monday."}
    main.dispatch(mail, FixtureMailbox(tmp_path), api, BidBoard(), [])
    assert started and started[0] != "decline_lookalike"


def test_a_crm_error_never_blocks_the_rfq(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))

    class Broken(Api):
        def sessions(self, stage=None):
            raise ConnectionError("backend down")
    main.dispatch({**R108, "body": "Please quote 3 pallets FRA-JFK 450 kg"}, FixtureMailbox(tmp_path), Broken([]),
                  BidBoard(), [])
    assert started and started[0] != "decline_lookalike"


HACKLOOP = ["hofmann-textilwerk", "rheintal-elektronik", "lindqvist-medtech", "weidner-spielwaren", "nordlicht-audio",
            "nordlicht-haulage", "meyer-optik", "meyer-industrie", "kraus-optik", "huber-optik", "schwarz-optik",
            "meridian-freightways", "ratedesk", "tracking", "alpha-pumpen", "brenner-pumpen"]


def test_real_hackloop_senders_never_imitate_each_other():
    addresses = [f"{name}@hackloop.mail" for name in HACKLOOP]
    assert [(a, b) for a in addresses for b in addresses if lookalike.strength(a, b)] == []


@pytest.mark.parametrize("sender, level", [
    ("hofmann-texti1werk@hackloop.mail", "strong"),
    ("hofmann-textiIwerk@hackloop.mail", "strong"),  # capital I for l
    ("hofmann-tеxtilwerk@hackloop.mail", "strong"),  # Cyrillic е
    ("hofmann--textilwerk@hackloop.mail", "strong"),
    ("hofmann-textilwerk@hackloop.co", "strong"),
    ("hofmann-textilwerk@gmail.com", "weak"),  # same name, another provider: only with a red flag
    ("Hofmann Textilwerk <x@evil.com>", None),  # display name alone: may be a real new contact
    ("hofmann-logistik@hackloop.mail", None),  # a new company with a similar name
    ("einkauf.hofmann-textilwerk@hackloop.mail", None),  # a colleague
])
def test_lookalikes_of_a_hackloop_customer(sender, level):
    assert lookalike.strength(sender, "hofmann-textilwerk@hackloop.mail") == level


@pytest.mark.parametrize("body", ["Please send us your quote for 300 kg FRA-JFK", "Delivery to our new address in Munich"])
def test_ordinary_rfq_wording_is_no_red_flag(body):
    assert not lookalike.RED_FLAG.search(body)


def test_a_declined_lookalike_never_becomes_a_known_customer(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))
    declined = {"id": 80, "customer": "nordlicht.audio@nordlicht-audio.de", "outcome": "lost", "rfq": None}
    # the impostor writes again: still declined
    main.dispatch({**R108, "id": "m109", "thread_id": "m109"}, FixtureMailbox(tmp_path),
                  Api([{"id": 77, "customer": REAL}, declined]), BidBoard(), [])
    # the real customer's first RFQ after an impostor: never declined as the impostor's lookalike
    main.dispatch({**R108, "id": "m110", "thread_id": "m110", "from": REAL, "subject": "RFQ FRA-JFK",
                   "body": "Please quote 3 pallets, 450 kg, FRA to JFK."}, FixtureMailbox(tmp_path),
                  Api([declined]), BidBoard(), [])
    assert started[0] == "decline_lookalike" and started[1] != "decline_lookalike"
