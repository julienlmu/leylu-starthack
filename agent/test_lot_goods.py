"""Session 205: each lot of a multi-lot quote keeps its own goods ("11 pieces of machine parts" for lot 2), never lot 1's."""
import shapes

BODY = ("Dear Sir or Madam,\n\nCould you please quote the cheapest air freight option for each of the two shipments "
        "below? Both will be ready for pickup at our site in 85122 (Ingolstadt), Germany, on 2026-11-27.\n\n"
        "1. Shipment 1 is bound for BKK (Bangkok, TH) and consists of 11 pieces of electronic control units, with a "
        "gross weight of 1190 kg and a volume of 2.92 cbm.\n\n2. Shipment 2 is bound for SIN (Singapore, SG) and "
        "consists of 11 pieces of machine parts, with a gross weight of 145 kg and a volume of 1.14 cbm.\n\nPlease "
        "provide a separate all-in price in EUR for each shipment.\n\nKind regards\nJonas Kessler")
RFQ = {"origin": "MUC", "destination": "BKK", "ask": "cheapest", "commodity": "electronic control units",
       "ready_date": "2026-11-27", "pieces": [{"count": 11, "weight_kg": 1190 / 11}], "volume_m3": 2.92}


def test_each_lot_keeps_its_own_goods():
    lots = shapes.all_lots({"subject": "Air freight quote request - BKK and SIN", "body": BODY}, RFQ)
    assert [(lot["destination"], lot["commodity"]) for lot in lots] == [("BKK", "electronic control units"),
                                                                        ("SIN", "machine parts")]
    assert [round(lot["pieces"][0]["count"] * lot["pieces"][0]["weight_kg"]) for lot in lots] == [1190, 145]
    assert [lot["volume_m3"] for lot in lots] == [2.92, 1.14]


def test_no_goods_named_keeps_the_mails_goods():
    body = BODY.replace("11 pieces of machine parts", "11 pieces").replace("11 pieces of electronic control units",
                                                                           "11 pieces")
    lots = shapes.all_lots({"subject": "x", "body": body}, RFQ)
    assert [lot["commodity"] for lot in lots] == ["electronic control units"] * 2
