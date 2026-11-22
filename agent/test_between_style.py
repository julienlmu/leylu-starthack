"""QUOTE_STYLE=between (default): Ulas's "in-between" mails (docs/HUMAN_MAILS.md on ulas/human-mails). Short and casual
like `short`, personal like `a`; every fact from code, one amount, no model."""
import re
from datetime import date, timedelta

import pytest

import gate
import quote_style
import short_mail
import templates
import test_language

TODAY = date.today()
SOON = (TODAY + timedelta(days=2)).isoformat()
RFQ = {"origin": "FRA", "destination": "JFK", "pieces": [{"count": 2, "weight_kg": 300}], "contact_name": "Anna Weber",
       "language": "en", "dangerous_goods": False, "pickup": None, "ready_date": SOON, "commodity": "machine parts",
       "ask": "cheapest"}
OPTION = {"carrier": "Solace Air", "currency": "EUR", "total": 1308.21, "transit_days": 2, "pickup": None}
ISO = re.compile(r"\b20\d\d-\d\d-\d\d\b|\b\d{1,2}\.\d{1,2}\.")


@pytest.fixture(autouse=True)
def between(monkeypatch):
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "between")


def _quote(body, **rfq):
    text = templates.quote_text({**RFQ, **rfq}, OPTION, body)
    assert gate.MONEY.findall(text) == ["1,308.21"] and "EUR 1,308.21 all in" in text, text
    assert "Solace Air" in text and "FRA" in text and "JFK" in text and not ISO.search(text), text
    return text


def test_is_the_default():
    from pathlib import Path
    assert 'os.environ.get("QUOTE_STYLE", "between")' in Path(quote_style.__file__).read_text()


def test_plain_request_airport_to_airport():
    text = _quote("Hi, 2 pallets of machine parts FRA to JFK please.\n\nAnna")
    assert text.startswith("Hi Anna,\n\nfor your 2 pallets of machine parts I can do Solace Air from Frankfurt (FRA) "
                           "to New York (JFK) for EUR 1,308.21 all in.")
    assert "fly " in text and "land around" in text
    assert text.endswith("just reply and I'll book it, space gets confirmed then.\n\ncheers,\nLena")


def test_small_talk_gets_one_line_and_door_pickup_names_the_town():
    text = _quote("Hi Lena, hope your week is going well! 3 crates of adhesives from Bad Homburg please.\n\nKlaus",
                  contact_name="Klaus", commodity="adhesives", pieces=[{"count": 3, "weight_kg": 100}],
                  pickup={"address": "Am Kurpark 3, 61348 Bad Homburg"})
    assert text.startswith("Hi Klaus,\n\nall good here, thanks, hope yours is too! For your 3 crates of adhesives")
    assert "pickup in Bad Homburg included. If that works for you, we can collect " in text and "should land around" in text


def test_fastest_and_formal_with_a_title_they_wrote():
    text = _quote("Dear Sir or Madam,\n\nplease quote the fastest option for 8 crates of spare parts.\n\n"
                  "Kind regards,\nMs Anna Weber", ask="fastest", pieces=[{"count": 8, "weight_kg": 50}],
                  commodity="spare parts")
    assert text.startswith("Hello Ms Weber,\n\nthank you for your request. Fastest I've got for your 8 crates of spare "
                           "parts is Solace Air")
    assert text.endswith("space is confirmed at booking.\n\nbest regards,\nLena")
    assert _quote("Dear Sir or Madam,\n\nquote please.\n\nKind regards,\nAnna Weber").startswith("Hello Anna Weber,")


def test_dangerous_goods_ask_for_the_papers_without_claiming_a_packing_list():
    text = _quote("Hi, 4 crates of spray cans, UN1950.\n\nSara", dangerous_goods=True, contact_name="Sara",
                  pieces=[{"count": 4, "weight_kg": 200}], commodity="maintenance spray cans")
    assert "your 4 crates of maintenance spray cans" in text and "four maintenance spray cans" not in text
    assert "Shipper's Declaration for Dangerous Goods" in text and "MSDS" in text and "packing list" not in text
    assert gate.finish(text, {"sentences": [], "chosen": OPTION}, {**RFQ, "dangerous_goods": True})[1] == []


@pytest.mark.parametrize("body, want", [("one box of spare parts", "your box of machine parts"),
                                        ("1 crate", "your crate of machine parts"),
                                        ("please quote", "your 80 kg of machine parts")])
def test_one_piece_is_never_your_1_piece(body, want):
    text = _quote(body, pieces=[{"count": 1, "weight_kg": 80}])
    assert want in text and "1 piece" not in text and "1 box" not in text


def test_reference_and_generic_goods():
    text = _quote("PO-4711, 2 boxes", customer_reference="PO-4711", commodity="general cargo")
    assert "re your PO-4711: for your 2 boxes I can do" in text


def test_german_informal_sender_stays_sie():
    text = templates.quote_text({**RFQ, "language": "de", "contact_name": "Jürgen Maier", "commodity": "Maschinenteile",
                                 "origin": "MUC", "destination": "ORD", "pickup": {"address": "Hauptstr. 1, 80331 München"}},
                                OPTION, "Hallo Lena,\n\nkannst du 2 Paletten Maschinenteile anbieten?\n\nJürgen")
    assert text.startswith("Hallo Jürgen,\n\nfür Ihre 2 Paletten Maschinenteile kann ich Solace Air von München (MUC) "
                           "nach Chicago (ORD) anbieten, EUR 1,308.21 all-in, Abholung in München inklusive. Wenn es Ihnen passt, holen wir ")
    assert text.endswith("\n\nviele Grüße\nLena") and "deine" not in text and not ISO.search(text)


def test_booked_confirmed_and_tracking_in_the_same_voice():
    booking = {"airline": "Solace Air", "booking_reference": "BK-1A2B3C4D", "status": "confirmed"}
    session = {"rfq": RFQ, "booking": booking, "quote": OPTION, "status_updates": []}
    booked = templates.booking_text(RFQ, booking)
    assert booked == ("Hi Anna,\n\ndone, it's booked with Solace Air, FRA to JFK, ref BK-1A2B3C4D. I'll let you know "
                      "as soon as they confirm.\n\ncheers,\nLena")
    assert templates.booking_confirmed_text(session).startswith("Hi Anna,\n\nSolace Air just confirmed BK-1A2B3C4D")
    tracking = templates.tracking_text(session)
    assert "BK-1A2B3C4D" in tracking and "Solace Air" in tracking and not ISO.search(tracking)
    assert tracking.endswith("cheers,\nLena")
    formal = templates.booking_text({**RFQ, "formal": True}, booking)
    assert formal.startswith("Hello Anna Weber,") and formal.endswith("best regards,\nLena")
    for text in (templates.tracking_unknown_text("en"), templates.reprice_text(RFQ, OPTION),
                 templates.tracking_many_text([session, session], "en")):
        assert text.endswith("cheers,\nLena") and not ISO.search(text), text


@pytest.mark.parametrize("lang", test_language.NATIVE)
@pytest.mark.parametrize("dg", [False, True])
def test_every_template_language_still_answers_in_its_language(lang, dg, monkeypatch):
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: pytest.fail("no model call for a template language"))
    test_language._check(lang, dg, test_language._mails(lang, dg))
    rfq = {**test_language.RFQ, "language": lang, "dangerous_goods": dg}
    text = templates.quote_text(rfq, {**test_language.QUOTE, "pickup": None})
    assert gate.MONEY.findall(text) == ["2,345.67"] and "EUR 2,345.67" in text
    if dg:
        assert "MSDS" in text and test_language.SDDG in text
    if lang != "en":
        assert not test_language.ENGLISH.search(text.replace(test_language.SDDG, "")), text


def test_short_still_switches_back(monkeypatch):
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "short")
    assert "Space gets confirmed when I book" in templates.quote_text(RFQ, OPTION)
    assert short_mail._sign("en").startswith("Thanks,")


@pytest.mark.parametrize("lang,formal_body,casual_body", [
    ("fr", "Bonjour,\noffre svp\nCordialement,\nClaire Dubois", "Salut, comment ça va ? un prix svp\nClaire Dubois"),
    ("es", "Estimados señores:\ncotización\nAtentamente,\nAna Pérez", "Hola, ¿cómo está? precio\nAna Pérez"),
    ("it", "Gentile Signora,\nofferta\nCordiali saluti,\nMarco Rossi", "Ciao, come sta? prezzo\nMarco Rossi"),
    ("nl", "Geachte heer,\nofferte\nMet vriendelijke groet,\nJan de Vries", "Hoi, hoe gaat het? prijs\nJan de Vries"),
    ("pt", "Prezados,\ncotação\nAtenciosamente,\nJoão Silva", "Olá, tudo bem? preço\nJoão Silva"),
    ("tr", "Sayın yetkili,\nteklif\nSaygılarımla,\nDeniz Yılmaz", "Merhaba, nasılsınız? fiyat\nDeniz Yılmaz")])
def test_other_languages_formal_sender_and_small_talk(lang, formal_body, casual_body):
    rfq = {**RFQ, "language": lang, "dangerous_goods": True, "ready_date": (TODAY + timedelta(days=12)).isoformat()}
    for body, is_formal in ((formal_body, True), (casual_body, False)):
        text = short_mail.between_quote(lang, rfq, OPTION, "EUR 1,308.21", True, body, today=TODAY)
        assert gate.MONEY.findall(text) == ["1,308.21"] and not ISO.search(text), text
        assert "Solace Air" in text and "MSDS" in text and test_language.SDDG in text, text
        assert text.endswith(short_mail.BETWEEN_SIGN[lang][is_formal]), text
        assert is_formal or short_mail.BETWEEN[lang]["chat"][1:] in text, text


@pytest.mark.parametrize("lang,body,want", [
    ("en", "3 pcs machine parts please", "your 450 kg of machine parts"),
    ("de", "3 Stück Maschinenteile", "Ihre 450 kg Maschinenteile"),
    ("fr", "3 colis aérosols", "vos 450 kg d'aérosols"),
    ("tr", "3 parça makine parçası", "450 kg makine parçası için"),
    ("it", "8 pallet di ricambi", "i suoi 3 pallet di ricambi"),
    ("pt", "3 paletes de peças", "as suas 3 paletes de peças"),
    ("es", "3 cajas de repuestos", "sus 3 cajas de repuestos"),
    ("nl", "3 dozen onderdelen", "uw 3 dozen"),
    ("tr", "3 sandık makine parçası", "3 sandık makine parçası için")])
def test_no_packing_word_means_the_weight_and_a_packing_word_is_said_back_in_their_language(lang, body, want):
    goods = {"en": "machine parts", "de": "Maschinenteile", "fr": "aérosols", "tr": "makine parçası", "it": "ricambi",
             "pt": "peças", "es": "repuestos", "nl": "onderdelen"}[lang]
    rfq = {**RFQ, "language": lang, "commodity": goods, "pieces": [{"count": 3, "weight_kg": 150}]}
    text = short_mail.between_quote(lang, rfq, OPTION, "EUR 1,308.21", False, f"Hi,\n{body}\n\nX", today=TODAY)
    assert want in text and "pieces of" not in text and "parça makine" not in text.replace("sandık makine", ""), text
    assert gate.MONEY.findall(text) == ["1,308.21"], text


def test_formal_plan_sentence_and_capitals_after_the_greeting():
    rfq = {**RFQ, "language": "fr", "commodity": "pièces", "pickup": {"address": "61348 Bad Homburg"}}
    text = short_mail.between_quote("fr", rfq, OPTION, "EUR 1,308.21", False,
                                    "Madame, Monsieur,\n\n2 palettes.\n\nCordialement,\nClaire Martin", today=TODAY)
    assert "Si cela vous convient, nous pouvons passer chercher la marchandise" in text and "ça" not in text, text
    assert "\n\nMerci pour votre demande. Pour vos 2 palettes" in text and text.endswith("Cordialement,\nLena"), text
    casual = short_mail.between_quote("fr", rfq, OPTION, "EUR 1,308.21", False, "Salut,\n2 palettes\n\nClaire",
                                      today=TODAY)
    assert "\n\nPour vos 2 palettes" in casual and "Si ça vous convient" in casual and casual.endswith("À bientôt,\nLena")
    de = short_mail.between_quote("de", {**rfq, "language": "de", "commodity": "Teile"}, OPTION, "EUR 1,308.21", False,
                                  "Hallo,\n2 Paletten\n\nJürgen", today=TODAY)
    assert "\n\nfür Ihre 2 Paletten Teile" in de  # German keeps the lowercase after "Hallo Jürgen,"
