from datetime import date

import pytest

import gate
import humanizer
import quote_style
import templates
from humanizer import a_quote_text, b_quote_text, greeting, tone

TODAY = date(2026, 11, 21)
KLAUS = ("Hi there,\n\nHope your week's going well. Could you send me an all-in price in EUR for the fastest air freight "
         "option from STR to EZE (Buenos Aires, AR)?\n\nCould you also let me know the latest drop-off time at STR and "
         "when the shipment would arrive at EZE?\n\nThanks for checking!\n\nCheers,\nKlaus Weidner\nWeidner Spielwaren GmbH")
SONNBERG = ("Dear Sir or Madam,\n\nCould you please quote the fastest air freight option to JFK? Pickup at our site in "
            "61018 (Bad Homburg), Germany.\n\nKind regards\nAnna Sonnberg\nSonnberg Kaffeeroesterei GmbH")
RFQ = {"origin": "STR", "destination": "EZE", "ask": "fastest", "ready_date": "2026-11-26", "language": "en",
       "pickup": None, "contact_name": "Klaus Weidner", "pieces": [{"count": 12, "weight_kg": 102.3}],
       "commodity": "textile samples", "dangerous_goods": False, "customer_reference": None}
OPTION = {"carrier": "Meridian Freightways", "currency": "EUR", "total": 8053.32, "transit_days": 2, "pickup": None}
DOOR = {**RFQ, "origin": "FRA", "destination": "JFK", "contact_name": "Anna Sonnberg",
        "pickup": {"address": "61018, Bad Homburg, Germany", "zone": "61"}}


def test_tone_and_greeting_mirror_the_customer():
    assert tone(KLAUS) == "casual" and tone(SONNBERG) == "formal"
    assert tone("Hello,\n\nplease quote.\n\nViele Gruesse / Many greetings\nDeniz Yilmaz") == "neutral"
    assert greeting("Klaus Weidner", "casual", "en") == "Hi Klaus,"
    assert greeting("Anna Sonnberg", "formal", "en") == "Dear Ms Sonnberg,"
    assert greeting("Deniz Yilmaz", "formal", "en") == "Dear Deniz Yilmaz,"  # unsure of the title: no guess
    assert greeting(None, "formal", "de") == "Sehr geehrte Damen und Herren,"
    assert greeting("Jonas Kessler", "formal", "de") == "Sehr geehrter Herr Kessler,"


def test_a_answers_the_questions_and_the_small_talk_with_one_amount():
    text = a_quote_text(RFQ, OPTION, KLAUS, TODAY)
    assert text.startswith("Hi Klaus,\n\n") and text.endswith("Best,\nLena\nLeylü Air Freight")
    assert "hope" in text.split("\n\n")[1].lower()  # small talk answered once
    assert "Thursday 26 November" in text and "Saturday 28 November" in text  # earliest departure + arrival
    assert "cut-off" in text and "confirm it with the airline" in text and ":00" not in text  # no invented clock time
    assert gate.MONEY.findall(text) == ["8,053.32"] and "EUR 8,053.32" in text
    assert "reply" in text and "!" not in text and "\n- " not in text and "finds you well" not in text


def test_a_formal_door_to_airport_names_the_town_and_dg_papers():
    text = a_quote_text({**DOOR, "dangerous_goods": True}, OPTION, SONNBERG, TODAY)
    assert text.startswith("Dear Ms Sonnberg,") and "Kind regards," in text
    assert "Bad Homburg" in text and "Shipper's Declaration for Dangerous Goods" in text and "MSDS" in text
    assert gate.MONEY.findall(text) == ["8,053.32"]
    _, findings = gate.finish(text, {"sentences": [], "chosen": OPTION}, {**DOOR, "dangerous_goods": True})
    assert findings == []


def test_a_is_deterministic_and_varies_between_requests():
    assert a_quote_text(RFQ, OPTION, KLAUS, TODAY) == a_quote_text(RFQ, OPTION, KLAUS, TODAY)
    texts = {a_quote_text({**RFQ, "customer_reference": f"R{i}"}, OPTION, "Hello,\n\nplease quote.", TODAY)
             for i in range(8)}
    assert len(texts) > 2


def test_a_german():
    rfq = {**DOOR, "language": "de", "contact_name": "Katharina Brandt",
           "pickup": {"address": "Landsberger Straße 12, 80339 München", "zone": "80"}, "origin": "MUC"}
    text = a_quote_text(rfq, OPTION, "Sehr geehrte Damen und Herren,\n\nbitte ein Angebot.", TODAY)
    assert text.startswith("Sehr geehrte Frau Brandt,\n\n") and "in München" in text and "Mit freundlichen Grüßen" in text
    assert "Donnerstag, 26. November" in text and gate.MONEY.findall(text) == ["8,053.32"]


def _model(mail):
    return lambda *a, **k: ({"mail": mail}, 0.00013)


def test_b_inserts_the_price_and_signs(monkeypatch):
    draft = ("Hi Klaus,\n\nThanks, all good here. Meridian Freightways leaves Stuttgart on Thursday 26 November and "
             "lands in Buenos Aires on Saturday 28 November, 2 days in transit. I'll confirm the exact cut-off with the "
             "airline once booked. The all-in price is {PRICE} EUR. Just reply to this email to book.\n\nBest,\nLena")
    monkeypatch.setattr(humanizer.llm, "chat_json", _model(draft))
    text = b_quote_text(RFQ, OPTION, KLAUS, TODAY)
    assert "is EUR 8,053.32. Just" in text and text.endswith("Best,\nLena\nLeylü Air Freight")


@pytest.mark.parametrize("draft", [
    "Hi Klaus, it leaves at 14:30 on Thursday 26 November. Price {PRICE}. Reply to book. " + "word " * 40,  # clock time
    "Hi Klaus, {PRICE} or {PRICE}. Reply to book. " + "word " * 40,  # two prices
    "Hi Klaus, {PRICE} plus EUR 120.00 handling. Reply to book. " + "word " * 40,  # a second amount
    "Hi Klaus, the price is {PRICE}. " + "word " * 40,  # no way to accept
])
def test_b_falls_back_to_a_when_the_model_breaks_a_rule(monkeypatch, draft):
    monkeypatch.setattr(humanizer.llm, "chat_json", _model(draft))
    assert b_quote_text(RFQ, OPTION, KLAUS, TODAY) == a_quote_text(RFQ, OPTION, KLAUS, TODAY)


def test_b_falls_back_without_dg_papers_or_on_errors(monkeypatch):
    dg = {**RFQ, "dangerous_goods": True}
    monkeypatch.setattr(humanizer.llm, "chat_json", _model("Hi Klaus, the price is {PRICE}. Reply to book. " + "x " * 50))
    assert b_quote_text(dg, OPTION, KLAUS, TODAY) == a_quote_text(dg, OPTION, KLAUS, TODAY)

    def down(*a, **k):
        raise TimeoutError("gateway")
    monkeypatch.setattr(humanizer.llm, "chat_json", down)
    assert b_quote_text(RFQ, OPTION, KLAUS, TODAY) == a_quote_text(RFQ, OPTION, KLAUS, TODAY)


def test_quote_style_switch(monkeypatch):
    classic = templates.quote_text(RFQ, OPTION, KLAUS)
    assert "All-in price: EUR 8,053.32" in classic  # default unchanged
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "a")
    assert templates.quote_text(RFQ, OPTION, KLAUS).startswith("Hi Klaus,\n\n")
    assert "Prix tout compris" in templates.quote_text({**RFQ, "language": "fr"}, OPTION, KLAUS)  # fr: classic
    monkeypatch.setattr(humanizer, "a_quote_text", lambda *a, **k: 1 / 0)
    assert templates.quote_text(RFQ, OPTION, KLAUS) == classic  # any error: classic wording


def test_signature_name_without_a_closing():
    assert templates.signature_name("Hi,\n\nplease quote.\n\nSara\nLindqvist Medtech") == "Sara"
    assert templates.signature_name("Hi,\n\nplease quote.\n\nMira Petersen\nNordlicht Audio") == "Mira Petersen"
    assert templates.signature_name("Hi,\n\nplease quote.\n\nLindqvist Medtech") is None
    assert templates.signature_name("Hi,\n\nplease quote.\n\nACME GmbH\nEinkauf") is None
