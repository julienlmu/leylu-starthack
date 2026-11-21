"""Ulas's docs/HACKATHON_GAPS.md: 5U tests WHERE and HOW information arrives. Top items as guards."""
import pytest

import booking_agent
import dg
import router
from inbox import normalize
from test_booking_tracking import REPLY, SESSION, FakeApi
from inbox import FixtureMailbox


@pytest.mark.parametrize("raw, plain", [
    ("U​N1133 adhesives", "UN1133 adhesives"),          # zero-width space inside the UN number
    ("FRА to JFK", "FRA to JFK"),                        # Cyrillic A in an IATA code
    ("ＵＮ１１３３, ７１５ kg", "UN1133, 715 kg"),              # full-width
    ("٧١٥ kg", "715 kg"),                      # Arabic-Indic digits
    ("2.4 m³", "2.4 m3"),
    ("Привет, это Москва", "Привет, это Москва"),             # a real Russian mail keeps its letters
    ("Grüße aus München", "Grüße aus München"),
])
def test_every_mail_is_plain_text_before_any_rule(raw, plain):
    assert normalize(raw) == plain


def test_hidden_characters_no_longer_hide_dg():
    assert dg.dg_info(normalize("U​N1133, 3 drums")) == "UN1133"
    assert dg.dg_info(normalize("ＵＮ３４８０ batteries")) == "UN3480"


@pytest.mark.parametrize("reply", ["👍", "✅", "👌 thx", "🤝", "✔️"])
def test_an_emoji_alone_is_a_yes(reply):
    assert booking_agent.read_intent(reply)[0] == "accept"


def test_a_mail_from_our_own_address_is_never_an_rfq():
    mail = {"from": "Leylü <leylu@hackloop.mail>", "to": "leylu@hackloop.mail", "subject": "Re: Air freight quote",
            "body": "3 pallets, 400 kg, FRA to JFK. Please quote."}
    assert router.route(mail, set(), known_thread=False) == "other"


def test_a_new_request_inside_the_thread_goes_to_a_person_not_to_the_booking(tmp_path):
    box, api = FixtureMailbox(tmp_path), FakeApi([SESSION])
    mail = {**REPLY, "body": "Thanks! Also, can you quote another shipment: 2 pallets, 300 kg to ORD?"}
    booking_agent.handle_customer_reply(mail, box, api, SESSION)
    assert api.booked == [] and box.sent == [] and api.sessions[17].get("needs_human")
    assert "needs_human" in api.events


@pytest.mark.parametrize("body", ["Thanks, another question: is pickup included?", "Yes please, book it.",
                                  "Another thing: the new pickup address is Hauptstr. 5."])
def test_ordinary_replies_are_not_new_requests(body):
    text = booking_agent.latest_text(body)
    assert not (booking_agent.NEW_REQUEST.search(text) and booking_agent.CARGO_FACT.search(text))
