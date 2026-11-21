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


# ---- Ulas's second pass: slang / formal wording and word order --------------------------------------------------

NOT_A_YES = ["book it? no, we won't", "booking, that we won't do", "Please confirm your offer is valid until Friday.",
             "Please confirm the offer is still valid, then we decide.", "Please confirm the quote is for 11 pieces.",
             "Please confirm your offer includes pickup.", "Please confirm the booking date with the airline first.",
             "Bitte bestätigen Sie, dass das Angebot bis Freitag gilt.", "Please confirm you can do 3 pallets.",
             "please confirm pickup on Monday", "Attached the DG declaration, please confirm receipt."]
A_YES = ["We confirm the booking.", "Please confirm the booking.", "Yes, please book.", "Please confirm.", "Confirmed!",
         "Confirm the order, thanks", "Wir bestätigen die Buchung.", "Bestätigt.", "lgtm", "say less", "works for me",
         "We are agreeable", "Kindly do the needful", "righto", "great, another price hike... fine, book it"]


@pytest.mark.parametrize("reply", NOT_A_YES)
def test_never_a_booking(reply, monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a, **k: ({"intent": "question"}, 0.0))
    assert booking_agent.read_intent(reply)[0] != "accept"


@pytest.mark.parametrize("reply", A_YES)
def test_still_a_yes_by_rules(reply):
    assert booking_agent.read_intent(reply) == ("accept", 0.0)


@pytest.mark.parametrize("text", ["Zephyr, please don't use them.", "Anyone but Zephyr Steppe Cargo please.",
                                  "We'd rather not have Zephyr Steppe Cargo.", "Lumen Air Cargo is fine, Zephyr not."])
def test_airline_bans_in_any_word_order(text):
    import constraints
    from carriers import load_carriers
    assert "Zephyr Steppe Cargo" in constraints.read(text, load_carriers())["excluded"]


@pytest.mark.parametrize("text", ["We had Zephyr last time, no problems.", "Zephyr not available? then Lumen.",
                                  "Lumen or Zephyr, whichever is cheaper."])
def test_no_ban_where_none_is_meant(text):
    import constraints
    from carriers import load_carriers
    assert "Zephyr Steppe Cargo" not in constraints.read(text, load_carriers())["excluded"]


@pytest.mark.parametrize("text, code", [
    ("Sehr geehrte Damen und Herren, ... PS: please answer in English.", "en"), ("Bitte auf Englisch antworten.", "en"),
    ("Merci de répondre en anglais.", "en"), ("Por favor conteste en inglés.", "en"),
    ("Rispondete in inglese per favore.", "en"), ("Please reply in German, thanks.", "de"),
    ("Our English colleague will review it.", None), ("We ship to Germany in German packaging.", None),
    ("Answer by Friday please.", None)])
def test_the_language_the_customer_asks_us_to_answer_in(text, code):
    import extract
    assert extract.reply_language(None, text) == code


def test_the_models_reply_language_counts_when_the_rules_see_nothing():
    import extract
    raw = {**{k: None for k in extract.SCHEMA["required"]}, "pieces": [], "language": "de", "reply_language": "EN"}
    raw.update(dim_unit="cm", weight_unit="kg", volume_unit="m3", ask="cheapest", dangerous_goods=False)
    rfq, _ = extract.to_rfq(raw)
    assert rfq["language"] == "en" and rfq["mail_language"] == "de"
