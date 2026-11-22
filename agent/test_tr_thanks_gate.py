"""Session 131 (Turkish RFQ): the customer's "Teşekkürler Lena, havayolunun onayını bekliyorum" went to a person, and
the gate's lower-deck sentence went out in English inside the Turkish quote."""
import gate
import gate_lang
from booking_agent import handle_customer_reply
from inbox import FixtureMailbox
from test_booking_tracking import BOOKING, REPLY, SESSION, FakeApi


def test_thanks_in_other_languages_need_no_person(tmp_path):
    booked = {**SESSION, "stage": "booked", "booking": BOOKING}
    for body, person in (("Teşekkürler Lena, havayolunun onayını bekliyorum.", False),
                         ("Tesekkurler, sağolun.", False), ("Çok teşekkür ederim!", False),
                         ("Merci beaucoup, j'attends la confirmation de la compagnie.", False),
                         ("Muchas gracias, quedo a la espera de la confirmación.", False),
                         ("Grazie mille, attendo la conferma.", False), ("Dank je wel!", False),
                         ("Teşekkürler ama lütfen iptal edin.", True), ("Teşekkürler, ama hayır.", True),
                         ("Danke, bitte stornieren.", True)):
        box, api = FixtureMailbox(tmp_path), FakeApi([booked])
        handle_customer_reply({**REPLY, "body": body}, box, api, booked)
        assert ("needs_human" in api.events) is person, body
        assert api.booked == [], body


def test_gate_sentences_in_the_mail_language():
    for en, de in (gate.OVERSIZE, gate.BATTERY_SENTENCE, gate.LATE, gate.OVER_BUDGET, gate.LATE_BETWEEN,
                   gate.OVER_BUDGET_BETWEEN, gate.INSURED):
        for lang in gate_lang.LANGS:
            local = gate_lang.say(en, lang)
            assert local != en and not any(c.isdigit() for c in local), (lang, en)
    assert gate_lang.say("An untranslated sentence.", "tr") == "An untranslated sentence."  # never dropped


def test_the_turkish_quote_gets_the_turkish_oversize_sentence():
    from test_cargo_price_sweep import check
    piece = {"count": 1, "length": 320, "width": 120, "height": 180, "weight": 900, "weight_is_total": True,
             "volume": None, "volume_is_total": True}
    c = check("Merhaba,\n\n1 sandık, en ucuz lütfen.\n\nTeşekkürler", raw={"language": "tr", "pieces": [piece],
                                                                        "volume": None})
    assert "oversize" in c.codes
    assert "lower-deck" not in c.text and gate_lang.say(gate.OVERSIZE[0], "tr") in c.text
