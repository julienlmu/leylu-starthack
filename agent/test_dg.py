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



def test_lithium_batteries_are_dangerous_goods():
    assert dg_info("50 cartons of lithium-ion batteries for e-bikes") == "lithium batteries"


def test_packing_list_totals():
    from dg import attachment_totals
    assert attachment_totals(ROUND_10_PACKING_LIST + "\nTotal volume (cbm): | 2.65") == (715.0, 2.65)
    assert attachment_totals("nothing here") == (None, None)


def test_packing_list_beats_the_mail():
    from rfq_agent import _use_packing_list_totals
    rfq = {"volume_m3": None, "pieces": [{"count": 3, "length_cm": 60, "width_cm": 100, "height_cm": 47, "weight_kg": 200.0}]}
    notes = _use_packing_list_totals(rfq, ["Total gross weight (kg): | 715\nTotal volume (cbm): | 2.65"])
    assert round(rfq["pieces"][0]["weight_kg"] * 3, 2) == 715.0 and rfq["volume_m3"] == 2.65 and len(notes) == 2
    same = {"volume_m3": 2.65, "pieces": [{"count": 3, "length_cm": None, "width_cm": None, "height_cm": None,
                                          "weight_kg": 715 / 3}]}
    assert _use_packing_list_totals(same, ["Total gross weight (kg): | 715\nTotal volume (cbm): | 2.65"]) == []
