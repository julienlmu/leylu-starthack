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
                            "Olá Anna,", "Merhaba Anna,")) and text.endswith("\nLena")
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
    assert "Friday deadline" in gated and found == [] and gated.endswith("\nLena")
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
        assert 1 <= len(lines) <= 4 and not lines[-1].endswith(".") and text.endswith("\nLena")
    assert "Departed MUC on LM 401." in templates.tracking_text({"rfq": RFQ, "booking": BOOKING,
                                                                "status_updates": [{"text": "Departed MUC on LM 401"}]})


def test_classic_and_a_still_switch_back(monkeypatch):
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "classic")
    assert "All-in price: EUR 2,345.67" in templates.quote_text(RFQ, OPTION)


def test_tracking_keeps_the_not_left_yet_line_and_transit():
    future = {"rfq": {**RFQ, "ready_date": "2999-01-01"}, "booking": BOOKING, "quote": {"transit_days": 3}}
    text = templates.tracking_text(future)
    assert "hasn't left yet" in text and "2999-01-01" in text and "Landsberger" in text and "3 days" in text
    assert len(body_lines(text)) <= 4
    assert "hasn't left yet" not in templates.tracking_text({**future, "rfq": {**RFQ, "ready_date": "2020-01-01"}})


@pytest.mark.parametrize("lang", ["pl", "cs", "sv", "da", "nb", "no", "fi", "ja", "zh"])
@pytest.mark.parametrize("dg", [False, True])
def test_more_languages_keep_every_fact_and_the_gate_checks(lang, dg):
    rfq = {**RFQ, "language": lang, "dangerous_goods": dg}
    text = templates.quote_text(rfq, OPTION)
    assert gate.MONEY.findall(text) == ["2,345.67"] and "EUR 2,345.67" in text
    assert "Lumen Air Cargo" in text and "MUC" in text and "ORD" in text and "640 kg" in text
    assert "Thanks," not in text and text.endswith("\nLena") and not BANNED.search(text)
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
