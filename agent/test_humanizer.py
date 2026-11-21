import re
from datetime import date

import pytest

import gate
import humanizer
import quote_style
import templates
from humanizer import a_quote_text, b_quote_text, goods_phrase, greeting, tone

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


@pytest.fixture(autouse=True)
def _same_round(monkeypatch):
    monkeypatch.setattr(humanizer, "_round", lambda: 0)  # the wording rotates with the 6-minute round


def test_tone_and_greeting_mirror_the_customer():
    assert tone(KLAUS) == "casual" and tone(SONNBERG) == "formal"
    assert tone("Hello,\n\nplease quote.\n\nViele Gruesse / Many greetings\nDeniz Yilmaz") == "neutral"
    assert greeting("Klaus Weidner", "casual", "en") == "Hi Klaus,"
    assert greeting("Anna Sonnberg", "formal", "en") == "Dear Anna Sonnberg,"  # no title she didn't write herself
    assert greeting("Eva Huber", "formal", "en", "Mit freundlichen Grüßen\nDr. Eva Huber") == "Dear Dr Huber,"
    assert greeting("Jonas Kessler", "formal", "de", "Gruß, Herr Kessler") == "Sehr geehrter Herr Kessler,"
    assert greeting("Deniz Yilmaz", "formal", "en") == "Dear Deniz Yilmaz,"  # unsure of the title: no guess
    assert greeting(None, "formal", "de") == "Sehr geehrte Damen und Herren,"
    assert greeting("Jonas Kessler", "formal", "de") == "Guten Tag Jonas Kessler,"  # no guessed title


def test_a_answers_the_questions_and_the_small_talk_with_one_amount():
    text = a_quote_text(RFQ, OPTION, KLAUS, TODAY)
    assert text.startswith("Hi Klaus,\n\n") and text.endswith("\nLena Hartmann\nAir Export | Leylü Air Freight")
    assert "hope" in text.split("\n\n")[1].lower()  # small talk answered once
    assert "Friday 27 November" in text and "Sunday 29 November" in text  # flies the day after the ready date (#95)
    assert "cut-off" in text and "confirm it with the airline" in text and ":00" not in text  # no invented clock time
    assert gate.MONEY.findall(text) == ["8,053.32"] and "EUR 8,053.32" in text
    assert "reply" in text and "!" not in text and "\n- " not in text and "finds you well" not in text


def test_a_formal_door_to_airport_names_the_town_and_dg_papers():
    text = a_quote_text({**DOOR, "dangerous_goods": True}, OPTION, SONNBERG, TODAY)
    assert text.startswith("Dear Anna Sonnberg,")  # no guessed title
    assert any(f"\n\n{bye}\n" in text for bye in humanizer.EN["bye"]["formal"])
    assert "Bad Homburg" in text and "Shipper's Declaration for Dangerous Goods" in text and "MSDS" in text
    assert gate.MONEY.findall(text) == ["8,053.32"]
    _, findings = gate.finish(text, {"sentences": [], "chosen": OPTION}, {**DOOR, "dangerous_goods": True})
    assert findings == []


def test_a_is_deterministic_and_varies_between_requests():
    assert a_quote_text(RFQ, OPTION, KLAUS, TODAY) == a_quote_text(RFQ, OPTION, KLAUS, TODAY)
    texts = {a_quote_text(RFQ, OPTION, "Hello,\n\nplease quote.", TODAY, seq=i) for i in range(8)}
    assert len(texts) == 8  # the wording rotates with the round


def test_a_german():
    rfq = {**DOOR, "language": "de", "contact_name": "Katharina Brandt",
           "pickup": {"address": "Landsberger Straße 12, 80339 München", "zone": "80"}, "origin": "MUC"}
    text = a_quote_text(rfq, OPTION, "Sehr geehrte Damen und Herren,\n\nbitte ein Angebot.", TODAY)
    assert text.startswith("Guten Tag Katharina Brandt,\n\n") and "in München" in text
    assert any(f"\n\n{bye}\n" in text for bye in humanizer.DE["bye"]["formal"])
    assert "Donnerstag, 26. November" in text and gate.MONEY.findall(text) == ["8,053.32"]


def _model(mail):
    return lambda *a, **k: ({"mail": mail}, 0.00013)


def test_b_inserts_the_price_and_signs(monkeypatch):
    draft = ("Hi Klaus,\n\nThanks, all good here. Meridian Freightways leaves Stuttgart on Friday 27 November and "
             "lands in Buenos Aires on Sunday 29 November, 2 days in transit. I'll confirm the exact cut-off with the "
             "airline once booked. The all-in price is {PRICE} EUR. Just reply to this email to book.\n\nBest,\nLena")
    monkeypatch.setattr(humanizer.llm, "chat_json", _model(draft))
    text = b_quote_text(RFQ, OPTION, KLAUS, TODAY)
    assert "is EUR 8,053.32. Just" in text and text.endswith("\nLena Hartmann\nAir Export | Leylü Air Freight")
    facts = humanizer.b_facts(RFQ, OPTION, KLAUS, TODAY, seq=3)
    assert facts["goods_phrase"] == "twelve textile samples (1228 kg)" and facts["structure"] in humanizer.B_STRUCTURES
    assert humanizer.check_b(f"Hi Klaus, {facts['goods_phrase']} for EUR 8,053.32. Reply to book. " + "one two " * 20,
                             OPTION, facts) == []  # the gross weight is a known number


@pytest.mark.parametrize("draft", [
    "Hi Klaus, it leaves at 14:30 on Thursday 26 November. Price {PRICE}. Reply to book. " + "word " * 40,  # clock time
    "Hi Klaus, {PRICE} or {PRICE}. Reply to book. " + "word " * 40,  # two prices
    "Hi Klaus, {PRICE} plus EUR 120.00 handling. Reply to book. " + "word " * 40,  # a second amount
    "Hi Klaus, the price is {PRICE}. " + "word " * 40,  # no way to accept
    "Hi Klaus, {PRICE} for your 1.86 cbm. Reply to book. " + "word " * 40,  # a volume: a second decimal
    "Dear Mr Weidner,\n\nthe price is {PRICE}. Reply to book. " + "word " * 40,  # a title he didn't write
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


def test_goods_phrase_grammar():
    assert goods_phrase(4, "handheld measuring devices", 378, "en") == "four handheld measuring devices (378 kg)"
    assert goods_phrase(8, "spare parts for packaging machines", 911, "en") == \
        "eight spare parts for packaging machines (911 kg)"
    assert goods_phrase(11, "sports equipment", 349, "en") == "eleven pieces of sports equipment (349 kg)"
    assert goods_phrase(12, "printed marketing material", 676, "en") == \
        "twelve pieces of printed marketing material (676 kg)"
    assert goods_phrase(3, "industrial adhesives", None, "en") == "three pieces of industrial adhesives"
    assert goods_phrase(1, "gas analysers", 40, "en") == "gas analyser (40 kg)"
    assert goods_phrase(16, "boxes", 1235, "en") == "16 boxes (1235 kg)"
    assert goods_phrase(4, "Ersatzteile", 620, "de") == "Ihre vier Packstücke Ersatzteile (620 kg)"


SARA = ("Hello,\n\nplease quote air freight for this shipment:\n\n- Pickup: from our site at 81862 Munich South, Germany\n"
        "- Commodity: handheld measuring devices, 4 pieces\n- Gross weight: 378 kg\n- Volume: 1.86 cbm\n"
        "- Our shipper's letter of instruction is attached to this email\n\nSara\nLindqvist Medtech")


def _sentences(text):
    return [s for p in text.split("\n\n")[1:-1] for s in re.split(r"(?<=[.!?])\s+", p) if s]


def test_a_acknowledges_the_attachment_names_the_basis_and_signs_in_full():
    rfq = {**DOOR, "contact_name": "Sara", "pieces": [{"count": 4, "weight_kg": 94.5}],
           "commodity": "handheld measuring devices", "excluded_airlines": ["Zephyr Steppe Cargo", "ZS"]}
    for seq in range(10):
        text = a_quote_text(rfq, OPTION, SARA, TODAY, seq=seq)
        assert "shipper's letter of instruction" in text and "four handheld measuring devices (378 kg)" in text
        assert "Zephyr Steppe Cargo" in text and "space" in text and "valid" not in text
        assert re.findall(r"\d[\d,]*\.\d+|\d+,\d{1,2}\b", text) == ["8,053.32"]  # no 1.86 cbm: the price is the only decimal
        assert text.endswith("\nLena Hartmann\nAir Export | Leylü Air Freight") and "@" not in text
        assert gate.finish(text, {"sentences": [], "chosen": OPTION}, rfq)[1] == []


def test_a_varies_across_ten_consecutive_rounds():
    dests = ["EZE", "JFK", "ORD", "MIA", "PVG", "SGN", "DEL", "DOH", "YYZ", "GRU"]
    bodies = [KLAUS, SONNBERG, SARA, "Hello,\n\nplease quote.", SONNBERG] * 2
    texts = [a_quote_text({**RFQ, "destination": d, "customer_reference": None if i % 3 else f"R-{i}",
                           "dangerous_goods": i == 4}, OPTION, body, TODAY, seq=100 + i)
             for i, (d, body) in enumerate(zip(dests, bodies))]
    openings = [_sentences(t)[0] for t in texts]
    assert len(set(openings)) == len(openings), openings
    counts = {}
    for t in texts:
        for s in _sentences(t):
            counts[s] = counts.get(s, 0) + 1
    assert max(counts.values()) <= 2, [s for s, n in counts.items() if n > 2]
    assert all(gate.MONEY.findall(t) == ["8,053.32"] for t in texts)
