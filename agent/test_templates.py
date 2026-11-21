import re

import pytest

from templates import T, booking_text, quote_text, signature_name

RFQ = {"origin": "MUC", "destination": "JFK", "ask": "fastest", "pickup": {"address": "Hauptstr. 1"},
       "customer_reference": "PO-4711",
       "pieces": [{"count": 3, "length_cm": 120, "width_cm": 80, "height_cm": 100, "weight_kg": 140}]}
OPTION = {"carrier": "Sky Air", "currency": "EUR", "total": 1856.0, "transit_days": 0.75}


@pytest.mark.parametrize("lang", [*T, "xx", None])
def test_quote_has_one_amount_in_every_language(lang):
    body = quote_text({**RFQ, "language": lang}, OPTION)
    assert re.findall(r"\d[\d,.]*\.\d{2}", body) == ["1,856.00"]  # transit 0.75 days must not leak as a decimal
    assert "EUR 1,856.00" in body and "{" not in body


def test_transit_in_hours_or_whole_days():
    assert "18 hours" in quote_text({**RFQ, "language": "en"}, OPTION)
    assert "2 days" in quote_text({**RFQ, "language": "en"}, {**OPTION, "transit_days": 2.4})


def test_booking_mail_follows_rfq_language():
    body = booking_text({**RFQ, "language": "de"}, {"airline": "Sky Air", "booking_reference": "BK-1"})
    assert "gebucht" in body and "BK-1" in body



def test_signature_name_from_real_rfqs():
    assert signature_name("Thank you.\n\nViele Gruesse / Many greetings\nDeniz Yilmaz\nRheintal Elektronik GmbH") == "Deniz Yilmaz"
    assert signature_name("…\n\nKind regards\nAnna Sonnberg\nHead of Purchasing and Logistics") == "Anna Sonnberg"
    assert signature_name("Best greetings from Regensburg\nTobias Auer\nVersand / Shipping") == "Tobias Auer"
    assert signature_name("Mit freundlichen Grüßen\nDr. Eva Huber") == "Eva Huber"
    assert signature_name("Please quote 3 pallets.") is None
    assert signature_name("Kind regards\nPO-4711 / Ref 2026") is None


def test_quote_greets_by_first_name_and_names_the_goods():
    body = quote_text({**RFQ, "language": "en", "contact_name": "Deniz Yilmaz", "commodity": "precision instruments"}, OPTION)
    assert body.startswith("Hi Deniz,") and "3 pieces of precision instruments" in body
    de = quote_text({**RFQ, "language": "de", "contact_name": "Deniz Yilmaz", "commodity": "Maschinenteile"}, OPTION)
    assert de.startswith("Hallo Deniz,") and "(Maschinenteile)" in de
    assert quote_text({**RFQ, "language": "en"}, OPTION).startswith("Hi,")
