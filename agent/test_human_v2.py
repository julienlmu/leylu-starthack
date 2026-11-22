"""HUMAN_V2: the quote answers the deadline and the file the customer asked for in one line each, and a fixed decline
greets by name. Amount, currency, airline, codes, dates and the reply line never change (5U reads them)."""
import re

import pytest

import import_trap
import mode_decline
import quote_style
import safety_net
import short_mail
import templates

NUM = re.compile(r"\d[\d.,:]*")
RFQ = {"origin": "CGN", "destination": "ORD", "ask": "cheapest", "language": "en", "contact_name": "Klaus Weidner",
       "pickup": {"address": "51871 (Bergisch Gladbach), Germany"}, "ready_date": "2026-11-27",
       "pieces": [{"count": 5, "weight_kg": 68.6}], "commodity": "furniture samples"}
OPTION = {"carrier": "Aurelia Air Cargo", "total": 1074.69, "currency": "EUR", "transit_days": 1.2,
          "pickup": {"carrier": "Elbkante", "transit_days": 0.5, "total": 100.0}}
BODY = ("Hi there,\n\nHope your week's going well. Could you send me an all-in air freight quote? They need to be at "
        "ORD by 2026-11-29 at the latest. Could you attach the offer as a PDF when you reply?\n\nCheers,\nKlaus")


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(short_mail, "HUMAN_V2", True)
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "between")  # the live default (conftest sets classic)


def both(rfq, option=OPTION, body=BODY, monkeypatch=None):
    on = templates.quote_text(rfq, option, body)
    short_mail.HUMAN_V2 = False
    try:
        off = templates.quote_text(rfq, option, body)
    finally:
        short_mail.HUMAN_V2 = True
    return off, on


def test_deadline_and_file_answered_numbers_unchanged():  # R179's mail asked both and got neither
    off, on = both({**RFQ, "arrive_by": "2026-11-29", "offer_doc": "pdf"})
    assert "in time for your deadline" in on and "the offer is attached as well" in on
    assert NUM.findall(on) == NUM.findall(off)
    assert on.replace(" That gets it there in time for your deadline.", "").replace(
        " As you asked, the offer is attached as well.", "").lower() == off.lower()  # + English capitals


def test_no_deadline_line_when_the_flight_is_late():
    _, on = both({**RFQ, "arrive_by": "2026-11-27"}, {**OPTION, "transit_days": 4})
    assert "deadline" not in on


def test_nothing_asked_nothing_added():
    off, on = both(RFQ)
    assert on.lower() == off.lower() and NUM.findall(on) == NUM.findall(off)  # only the English capitals


def test_a_form_is_not_called_attached():
    _, on = both({**RFQ, "offer_doc": "form"})
    assert "attached" not in on


@pytest.mark.parametrize("lang,line", [("de", "rechtzeitig zu Ihrem Termin"), ("fr", "à temps"),
                                       ("tr", "tarihe yetişiyor")])
def test_other_languages(lang, line):
    _, on = both({**RFQ, "language": lang, "arrive_by": "2026-11-29"}, body="")
    assert line in on


def test_off_restores_the_mail(monkeypatch):
    monkeypatch.setattr(short_mail, "HUMAN_V2", False)
    text = import_trap.decline_text("en")
    assert short_mail.named(text, RFQ, BODY) == text


@pytest.mark.parametrize("text", [import_trap.decline_text("en"), import_trap.lane_text("en"),
                                  mode_decline.decline_text("en"), safety_net.decline_text("en")])
def test_declines_greet_by_name(text):
    named = short_mail.named(text, RFQ, BODY)
    assert named.startswith("Hi Klaus,\n\n") and named.split("\n\n", 1)[1] == text.split("\n\n", 1)[1]


def test_formal_decline_formal_greeting_and_close():
    body = "Dear Sir or Madam,\n\nplease quote.\n\nKind regards\nMs Anna Weber"
    named = short_mail.named(mode_decline.decline_text("en"), {**RFQ, "contact_name": "Anna Weber"}, body)
    assert named.startswith("Hello Ms Weber,") and "cheers" not in named


def test_german_and_turkish_declines():
    de = short_mail.named(import_trap.decline_text("de"), {**RFQ, "language": "de"}, "Hallo,\n\nbitte Angebot.")
    assert de.startswith("Hallo Klaus,") or de.startswith("Guten Tag")
    tr = short_mail.named(import_trap.decline_text("tr"), {**RFQ, "language": "tr", "contact_name": "Sara"}, "Merhaba")
    assert tr.startswith("Merhaba Sara,\n\nTalebiniz")  # capital after the greeting, as in every Turkish mail


def test_no_name_no_change():
    text = mode_decline.decline_text("en")
    assert short_mail.named(text, {**RFQ, "contact_name": None}, BODY) == text


@pytest.mark.parametrize("sentence", ["The packing list is attached.",
                                      "- Our shipper's letter of instruction is attached to this email",
                                      "Our packing specification is attached."])
def test_their_own_attachment_is_no_ask(sentence):  # session 200: "As you asked, the offer is attached" to an SLI line
    body = f"Hello,\n\nplease quote MUC to DXB, 780 kg.\n{sentence}\n\nPlease reply with your all-in price in EUR.\n\nKind regards\nAnna"
    _, on = both({**RFQ, "offer_doc": "pdf"}, body=body)
    assert "attached" not in on


@pytest.mark.parametrize("sentence", ["Please attach your offer as a PDF to your reply.",
                                      "Please send your all-in price in EUR as a PDF attached to your reply.",
                                      "Could you attach the offer as a PDF when you reply?"])
def test_a_real_file_ask_keeps_the_line(sentence):
    _, on = both({**RFQ, "offer_doc": "pdf"}, body=f"Hi,\n\nplease quote.\n{sentence}\n\nCheers,\nKlaus")
    assert "the offer is attached as well" in on


def test_english_capitals():  # session 200: "collect tuesday", "just reply", "best regards,"
    from datetime import date
    body = "Hello,\n\nplease quote.\n\nKind regards\nAnna Sonnberg"
    text = templates.quote_text({**RFQ, "contact_name": "Anna Sonnberg", "ready_date": "2026-11-24"}, OPTION, body)
    paragraphs = text.split("\n\n")
    assert all(p[:1].isupper() for p in paragraphs), text
    assert "Best regards,\nLena" in text and "best regards" not in text
    short_mail.HUMAN_V2 = False
    try:
        assert "best regards,\nLena" in templates.quote_text({**RFQ, "contact_name": "Anna Sonnberg"}, OPTION, body)
    finally:
        short_mail.HUMAN_V2 = True


def test_english_weekday_capital():
    from datetime import date
    assert short_mail._when("en", date(2026, 11, 24), date(2026, 11, 22), True) == "Tuesday"
    assert short_mail._when("de", date(2026, 11, 24), date(2026, 11, 22), False) == "Dienstag"
