import re

from dg import dg_info
from templates import quote_text

ROUND_10_BODY = ("It's 3 pieces of industrial adhesives, with a gross weight of 715 kg and a total volume of 2.65 cbm. "
                 "The goods are general cargo, non-dangerous, and I've attached our packing specification.")
ROUND_10_PACKING_LIST = ("Packing Specification\nGoods description: | industrial adhesives\n"
                         "Total gross weight (kg): | 715\nDangerous goods: | UN1133, Class 3, Adhesives")


def test_the_attachment_beats_the_mail():
    assert dg_info(ROUND_10_BODY) is None  # "non-dangerous" in the mail alone
    assert dg_info(ROUND_10_BODY, ROUND_10_PACKING_LIST) == "UN1133, Class 3"


def test_no_false_alarms():
    assert dg_info("Dangerous goods: no\nClass 3 seats please") is None
    assert dg_info("No dangerous goods, machine parts, 3 pallets") is None
    assert dg_info("Dangerous goods: none") is None
    assert dg_info("Lithium batteries, Class 9, UN3480") == "UN3480, Class 9"
    assert dg_info("Gefahrgut: flammable liquid, class 3") == "Class 3"


def test_the_quote_asks_for_the_dg_documents_and_keeps_one_amount():
    rfq = {"origin": "FRA", "destination": "GRU", "ask": "cheapest", "pickup": None, "customer_reference": None,
           "language": "en", "contact_name": "Klaus Weidner", "commodity": "industrial adhesives",
           "dangerous_goods": True, "dg_info": "UN1133, Class 3",
           "pieces": [{"count": 3, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 238.3}]}
    body = quote_text(rfq, {"carrier": "Juniper Cargo Lines", "currency": "EUR", "total": 2685.35, "transit_days": 6})
    assert "MSDS" in body and "UN1133, Class 3" in body and "EUR 2,685.35" in body
    assert re.findall(r"\d[\d,.]*\.\d{2}", body) == ["2,685.35"]
