import re

from dg import dg_info
from templates import quote_text

ROUND_10_BODY = ("It's 3 pieces of industrial adhesives, with a gross weight of 715 kg and a total volume of 2.65 cbm. "
                 "The goods are general cargo, non-dangerous, and I've attached our packing specification.")
ROUND_10_PACKING_LIST = ("Packing Specification\nGoods description: | industrial adhesives\n"
                         "Total gross weight (kg): | 715\nDangerous goods: | UN1133, Class 3, Adhesives")


def test_the_attachment_beats_the_mail():
    assert dg_info(ROUND_10_BODY) == "adhesives"  # the goods alone are DG, whatever the mail claims
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
    assert "MSDS" in body and body.count("MSDS") == 1 and "EUR 2,685.35" in body  # one DG paragraph
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



def test_round_11_pdf_text_is_dangerous_goods():
    sli = ("Shipper's Letter of Instruction\nGoods description: maintenance spray cans\nTotal gross weight (kg): 855\n"
           "Total volume (cbm): 3.74\nDangerous goods: UN1950, Class 2.1, Aerosols, flammable")
    assert dg_info("maintenance spray cans … general cargo, non-dangerous", sli) == "UN1950, Class 2.1"



def test_dg_goods_without_un_numbers():
    assert dg_info("Commodity: maintenance spray cans, 4 pieces") == "spray cans"
    assert dg_info("12 cartons of perfume samples") == "perfume"
    assert dg_info("machine parts and steel brackets") is None
    assert dg_info("Dangerous goods: no. Commodity: printed marketing material") is None


def test_no_false_alarm_from_a_no_answer_or_a_table_header():
    for text in ("Dangerous goods: Not restricted", "Dangerous goods: not applicable", "Dangerous goods: false",
                 "Dangerous goods: n/a", "Dangerous goods: non-hazardous",
                 "Item | Pieces | Dangerous goods | Gross weight\n1 | 3 | No | 715"):
        assert dg_info("machine parts, general cargo", text) is None, text
    assert dg_info("Dangerous goods: | UN1133, Class 3, Adhesives") == "UN1133, Class 3"  # xlsx cells still read


def test_negated_dg_words_are_no_alarm():
    assert dg_info("Goods: non-flammable cosmetics, not dangerous") is None
    assert dg_info("Spare parts, no lithium batteries included") is None
    assert dg_info("Tools without lithium-ion batteries, lithium-free packaging") is None
    assert dg_info("Laptops with lithium-ion batteries") == "lithium batteries"  # still DG
    assert dg_info("Perfume samples, non-flammable outer box") == "perfume"  # the goods themselves stay DG


def test_division_2_2_is_named_non_flammable_and_is_still_dangerous_goods():
    for text in ("Goods: CO2 cartridges, Class 2.2 non-flammable gas", "Hazard class 2.2 (non-flammable gas), 40 cylinders",
                 "Fire extinguishers, Class 2.2, non-flammable", "Goods are not flammable liquids but Class 3 per MSDS"):
        assert dg_info(text), text
    assert dg_info("non-flammable plastic housings, general cargo") is None  # #65's own case stays clean
