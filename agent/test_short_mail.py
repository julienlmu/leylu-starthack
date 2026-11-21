"""QUOTE_STYLE=short: one fixed short casual mail per kind; the facts are copied, never reworded (5U humanity bonus)."""
import re

import pytest

import gate
import quote_style
import templates

RFQ = {"origin": "MUC", "destination": "ORD", "pieces": [{"count": 3, "weight_kg": 213.4}], "contact_name": "Anna Berg",
       "language": "en", "dangerous_goods": False, "pickup": {"address": "Landsberger Str. 12, 80339 München"}}
OPTION = {"carrier": "Lumen Air Cargo", "currency": "EUR", "total": 2345.67, "transit_days": 3,
          "pickup": {"carrier": "Isarwelle", "total": 140.0}}
BOOKING = {"airline": "Lumen Air Cargo", "booking_reference": "BK-50NN8E8G", "status": "booked"}
BANNED = re.compile(r"hope this (email )?finds you|don'?t hesitate|zögern sie nicht|—|–|^\s*[-*•]\s", re.I | re.M)


@pytest.fixture(autouse=True)
def short(monkeypatch):
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "short")


def body_lines(text):
    return text.split("\n\n")[1].split("\n")


@pytest.mark.parametrize("lang", ["en", "de", "fr", "es", "it", "nl", "pt", "tr"])
@pytest.mark.parametrize("dg", [False, True])
def test_the_quote_is_short_casual_and_copies_every_fact(lang, dg):
    rfq = {**RFQ, "language": lang, "dangerous_goods": dg}
    text = templates.quote_text(rfq, OPTION)
    assert gate.MONEY.findall(text) == ["2,345.67"] and "EUR 2,345.67" in text
    assert "Lumen Air Cargo" in text and "MUC" in text and "ORD" in text and "640 kg" in text
    assert not BANNED.search(text)
    lines = body_lines(text)
    assert 2 <= len(lines) <= 4 and not lines[-1].endswith(".")  # the one fixed imperfection
    assert text.startswith(("Hi Anna,", "Hallo Anna,", "Bonjour Anna,", "Hola Anna,", "Ciao Anna,", "Hoi Anna,",
                            "Olá Anna,", "Merhaba Anna,")) and text.endswith("\nLena Hartmann, Leylü Air Freight")
    verdict = {"sentences": [], "chosen": OPTION}
    assert gate.finish(text, verdict, rfq)[1] == []  # one amount, currency named, DG papers asked when DG
    if dg:
        assert "MSDS" in text


def test_english_uses_contractions_and_no_name_means_plain_hi():
    text = templates.quote_text({**RFQ, "contact_name": None}, OPTION)
    assert text.startswith("Hi,\n\n") and "I'll" in text and "It's" in text


def test_the_gate_sentences_still_go_in_and_the_check_still_holds():
    text = templates.quote_text(RFQ, OPTION)
    gated, found = gate.finish(text, {"sentences": ["That gets them there before your Friday deadline."],
                                      "chosen": OPTION}, RFQ)
    assert "Friday deadline" in gated and found == [] and gated.endswith("\nLena Hartmann, Leylü Air Freight")
    broken, found = gate.finish(text.replace("2,345.67", "2,345.67 (EUR 2,205.67 plus 140.00 pickup)"),
                                {"sentences": [], "chosen": OPTION}, RFQ)
    assert any(f["code"] == "amounts" for f in found)  # two amounts would still be held


def test_a_usd_quote_keeps_its_currency():
    text = templates.quote_text(RFQ, {**OPTION, "currency": "USD", "total": 2790.7})
    assert "USD 2,790.70" in text and "EUR" not in text


def test_booking_confirmed_and_tracking_copy_airline_and_reference():
    for text in (templates.booking_text(RFQ, BOOKING),
                 templates.booking_confirmed_text({"rfq": RFQ, "booking": BOOKING}),
                 templates.tracking_text({"rfq": RFQ, "booking": BOOKING,
                                          "status_updates": [{"text": "Departed MUC on LM 401"}]})):
        assert "BK-50NN8E8G" in text and "Lumen Air Cargo" in text and not BANNED.search(text)
        lines = body_lines(text)
        assert 1 <= len(lines) <= 4 and not lines[-1].endswith(".") and text.endswith("\nLena Hartmann, Leylü Air Freight")
    assert "Departed MUC on LM 401." in templates.tracking_text({"rfq": RFQ, "booking": BOOKING,
                                                                "status_updates": [{"text": "Departed MUC on LM 401"}]})


def test_classic_and_a_still_switch_back(monkeypatch):
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "classic")
    assert "All-in price: EUR 2,345.67" in templates.quote_text(RFQ, OPTION)


def test_tracking_keeps_the_not_left_yet_line_and_transit():
    future = {"rfq": {**RFQ, "ready_date": "2999-01-01"}, "booking": BOOKING, "quote": {"transit_days": 3}}
    text = templates.tracking_text(future)
    assert "hasn't left yet" in text and "1 Jan" in text and "2999" not in text and "Landsberger" in text and "3 days" in text
    assert len(body_lines(text)) <= 4
    assert "hasn't left yet" not in templates.tracking_text({**future, "rfq": {**RFQ, "ready_date": "2020-01-01"}})


@pytest.mark.parametrize("lang", ["pl", "cs", "sv", "da", "nb", "no", "fi", "ja", "zh"])
@pytest.mark.parametrize("dg", [False, True])
def test_more_languages_keep_every_fact_and_the_gate_checks(lang, dg):
    rfq = {**RFQ, "language": lang, "dangerous_goods": dg}
    text = templates.quote_text(rfq, OPTION)
    assert gate.MONEY.findall(text) == ["2,345.67"] and "EUR 2,345.67" in text
    assert "Lumen Air Cargo" in text and "MUC" in text and "ORD" in text and "640 kg" in text
    assert "Thanks," not in text and text.endswith("\nLena Hartmann, Leylü Air Freight") and not BANNED.search(text)
    assert gate.finish(text, {"sentences": [], "chosen": OPTION}, rfq)[1] == []
    assert ("MSDS" in text and "Shipper's Declaration for Dangerous Goods" in text) == dg
    for mail in (templates.booking_text(rfq, BOOKING), templates.booking_confirmed_text({"rfq": rfq, "booking": BOOKING})):
        assert "BK-50NN8E8G" in mail and "Lumen Air Cargo" in mail and "Thanks," not in mail


def test_slavic_plurals_and_east_asian_greetings():
    import short_mail
    assert [short_mail._n(short_mail.GOODS["pl"], n) for n in (1, 3, 5, 12, 22)] == \
        ["1 sztukę", "3 sztuki", "5 sztuk", "12 sztuk", "22 sztuki"]
    assert short_mail._n(short_mail.DAYS["cs"], 5) == "5 dní"
    assert templates.quote_text({**RFQ, "language": "ja"}, OPTION).startswith("Anna様")
    assert templates.quote_text({**RFQ, "language": "zh"}, OPTION).startswith("Anna，您好")


# ---- a language without a template: translated once with placeholders, checked, cached; facts filled by code ----

KO = {"hi": "안녕하세요", "sign": "감사합니다,\nLena", "quote": "{carrier}이(가) {goods}을 {origin}에서 {destination}까지 {amount} 올인으로 운송할 수 있습니다{pickup}.{transit}",
      "goods_one": "{n}개", "goods_many": "{n}개", "pickup": ", 픽업 포함", "transit": " 운송 기간은 약 {n}입니다.",
      "day_one": "{n}일", "day_many": "{n}일", "reply": "예약 시 공간이 확정됩니다, 예라고 답해 주시면 바로 예약합니다",
      "booked": "{airline}로 예약 완료, {origin}에서 {destination}, 예약번호 {ref}. 확정되면 알려드릴게요",
      "confirmed": "{airline}이(가) {ref}을(를) 확정했습니다. 언제든 상태를 물어보세요",
      "dg": "위험물(DG)입니다: 픽업 전에 Shipper's Declaration for Dangerous Goods와 MSDS를 보내주세요."}


@pytest.fixture
def fresh_languages(monkeypatch, tmp_path):
    import short_mail
    monkeypatch.setattr(short_mail, "CACHE", tmp_path / "langs.json")
    monkeypatch.setattr(short_mail, "_tried", set())
    for table in (short_mail.HI, short_mail.SIGN, short_mail.QUOTE, short_mail.GOODS, short_mail.PICKUP,
                  short_mail.TRANSIT, short_mail.DAYS, short_mail.REPLY, short_mail.BOOKED, short_mail.CONFIRMED,
                  short_mail.DG):
        monkeypatch.setattr(short_mail, table is short_mail.DG and "DG" or [k for k, v in vars(short_mail).items()
                                                                             if v is table][0], dict(table))
    return short_mail


def test_a_new_language_is_translated_once_and_the_facts_come_from_code(fresh_languages, monkeypatch):
    calls = []
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: (calls.append(a[0]) or dict(KO), 0.0004))
    rfq = {**RFQ, "language": "ko", "dangerous_goods": True}
    text = templates.quote_text(rfq, OPTION)
    assert calls == ["mail_language"] and text.startswith("안녕하세요 Anna,")
    assert gate.MONEY.findall(text) == ["2,345.67"] and "EUR 2,345.67" in text and "Lumen Air Cargo" in text
    assert "MUC" in text and "ORD" in text and "MSDS" in text and gate.finish(text, {"sentences": [], "chosen": OPTION}, rfq)[1] == []
    templates.quote_text(rfq, OPTION)
    assert "BK-50NN8E8G" in templates.booking_text(rfq, BOOKING) and calls == ["mail_language"]  # once, then cached
    assert "ko" in __import__("json").loads(fresh_languages.CACHE.read_text())


@pytest.mark.parametrize("broken", [
    {"quote": KO["quote"].replace("{amount}", "2.345,67 유로")},          # the model touched the amount
    {"quote": KO["quote"].replace("{origin}", "프랑크푸르트")},            # a code turned into a city name
    {"dg": "위험물입니다."},                                              # DG names dropped
    {"reply": KO["reply"] + " 3일 안에"},                                 # a number of its own
    {"booked": KO["booked"].replace("{ref}", "")},                        # the booking reference dropped
])
def test_a_broken_translation_is_never_used(fresh_languages, monkeypatch, broken):
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: ({**KO, **broken}, 0.0004))
    text = templates.quote_text({**RFQ, "language": "ko"}, OPTION)
    assert text.startswith("Hi Anna,") and "EUR 2,345.67" in text  # English, facts intact


@pytest.mark.parametrize("code", ["un", "xx", "en", "e", "123"])
def test_no_call_for_non_languages(fresh_languages, monkeypatch, code):
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: pytest.fail("no translation call"))
    assert templates.quote_text({**RFQ, "language": code}, OPTION).startswith("Hi Anna,")


def test_a_failed_translation_is_tried_once_and_english_goes_out(fresh_languages, monkeypatch):
    calls = []
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(TimeoutError()))
    assert templates.quote_text({**RFQ, "language": "hu"}, OPTION).startswith("Hi Anna,")
    templates.quote_text({**RFQ, "language": "hu"}, OPTION)
    assert calls == [1]


def test_switched_off_means_english(fresh_languages, monkeypatch):
    monkeypatch.setattr(fresh_languages, "TRANSLATE", False)
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: pytest.fail("no call when off"))
    assert templates.quote_text({**RFQ, "language": "ko"}, OPTION).startswith("Hi Anna,")


@pytest.mark.parametrize("lang, kg", [("en", "1,674 kg"), ("de", "1674 kg"), ("fr", "1674 kg"), ("pl", "1674 kg"),
                                      ("ja", "1674 kg")])
def test_weights_have_no_english_thousands_comma_outside_english(lang, kg):
    """R73: in German "1,674 kg" reads as 1.674 kg."""
    rfq = {**RFQ, "language": lang, "pieces": [{"count": 11, "weight_kg": 152.181818}]}
    text = templates.quote_text(rfq, OPTION)
    assert kg in text and (lang == "en" or "1,674" not in text)


R79 = ("Hi,\n\nCould you quote the cheapest air freight option to MIA (Miami, US), including truck pickup from our site in "
       "35622 (Giessen), Germany? The shipment will be ready for pickup on 2026-11-25. When would it arrive?\n\n"
       "It's 5 pieces of automotive sensors, 638 kg gross and 3.93 cbm.\n\nSara")
RFQ79 = {"origin": "FRA", "destination": "MIA", "pieces": [{"count": 5, "weight_kg": 127.6}], "contact_name": "Sara",
         "language": "en", "dangerous_goods": False, "commodity": "automotive sensors", "ready_date": "2026-11-25",
         "pickup": {"address": "35622 (Giessen), Germany", "zone": None}}
OPT79 = {"carrier": "Solace Air Cargo", "currency": "EUR", "total": 1533.69, "transit_days": 6.2,
         "pickup": {"carrier": "Sternmeile", "total": 102.94, "transit_days": 0.5}}


def test_mail_human_answers_the_question_names_a_detail_and_signs_in_full():
    text = templates.quote_text(RFQ79, OPT79, R79)
    assert "automotive sensors" in text and "pickup in Giessen included" in text
    assert "Earliest arrival in Miami would be around" in text
    assert text.endswith("Thanks again for thinking of us.\nLena Hartmann, Leylü Air Freight")
    assert gate.MONEY.findall(text) == ["1,533.69"] and gate.finish(text, {"sentences": [], "chosen": OPT79}, RFQ79)[1] == []
    assert not body_lines(text)[-1].endswith(".")  # the reply line stays as it is


def test_mail_human_answers_awb_and_dropoff_in_our_own_voice_for_sie_and_du():
    """Our voice never copies the sender's (test_steady_voice.py): "Hallo Klaus," and the Sie closing for both."""
    rfq = {**RFQ79, "language": "de", "contact_name": "Klaus Hofmann", "pickup": None}
    sie = ("Sehr geehrte Damen und Herren,\nkönnen Sie uns ein Angebot machen? Wo können wir die Ware anliefern? "
           "Bitte nennen Sie die AWB.\nMit freundlichen Grüßen\nKlaus Hofmann")
    text = templates.quote_text(rfq, {**OPT79, "pickup": None}, sie)
    assert text.startswith("Hallo Klaus,") and "Cargo-Terminal von Solace Air Cargo" in text
    assert "AWB-Nummer" in text and text.endswith("Vielen Dank für Ihre Anfrage und viele Grüße\nLena Hartmann, Leylü Air Freight")
    du = templates.quote_text(rfq, {**OPT79, "pickup": None}, "Hallo Lena, kannst du mir ein Angebot schicken? Danke dir")
    assert du.startswith("Hallo Klaus,") and "dir" not in du.split() and du.endswith("viele Grüße\nLena Hartmann, Leylü Air Freight")


def test_no_question_no_extra_clause_and_digits_never_come_from_the_commodity():
    text = templates.quote_text({**RFQ79, "commodity": "UN3480 lithium batteries 18650"}, OPT79, "Please quote. Sara")
    assert "arrival" not in text and "18650" not in text and gate.MONEY.findall(text) == ["1,533.69"]


def test_mail_human_off_is_the_mail_before(monkeypatch):
    import short_mail
    monkeypatch.setattr(short_mail, "HUMAN", False)
    text = templates.quote_text(RFQ79, OPT79, R79)
    assert text.endswith("\nLena") and "arrival" not in text and "Giessen" not in text
