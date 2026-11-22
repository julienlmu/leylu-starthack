"""Saturday night traps: multi-shipment quotes (R89/R90), "book only the first", second thoughts after a yes (R88)."""
import booking_agent
import shapes

R90 = {"id": 1, "thread_id": 1, "from": "rheintal-elektronik@hackloop.mail", "subject": "Air freight quote request - RUH and GRU",
       "body": ("Hello,\n\nCould you please quote the fastest air freight option for each of these two shipments? Both are "
                "ready for pickup on 2026-11-28 at our site in 20674 Hamburg, Germany. Please arrange the truck from our "
                "site to the airport.\n\n1. Destination airport RUH (Riyadh, SA): sports equipment, 6 pieces, gross weight "
                "591 kg, volume 1.95 cbm.\n2. Destination airport GRU (Sao Paulo, BR): machine parts, 6 pieces, gross "
                "weight 1335 kg, volume 10.63 cbm.\n\nPlease send both quotes in the same reply, with a separate all-in "
                "price in EUR for each shipment rather than a combined price.\n\nThank you.\n\nDeniz Yilmaz"),
       "attachments": []}
RFQ90 = {"origin": "HAM", "destination": "RUH", "ask": "fastest", "pickup": {"address": "20674 Hamburg, Germany", "zone": None},
         "ready_date": "2026-11-28", "pieces": [{"count": 6, "weight_kg": 98.5}, {"count": 6, "weight_kg": 222.5}],
         "volume_m3": 12.58, "commodity": "sports equipment (RUH); machine parts (GRU)", "dangerous_goods": False,
         "language": "en", "contact_name": "Deniz Yilmaz"}


def test_r90_each_shipment_becomes_its_own_request():
    rfq = dict(RFQ90)
    missing, notes = shapes.before_pricing(rfq, R90, [])
    assert missing == [] and rfq["destination"] == "RUH" and rfq["pieces"][0]["count"] == 6
    assert rfq["pieces"][0]["weight_kg"] * 6 == 591 and rfq["volume_m3"] == 1.95
    [other] = rfq["other_lots"]
    assert other["destination"] == "GRU" and other["pieces"][0]["weight_kg"] * 6 == 1335 and other["volume_m3"] == 10.63


def test_multi_quote_off_hands_over_as_before(monkeypatch):
    monkeypatch.setattr(shapes, "MULTI_QUOTE", False)
    rfq = dict(RFQ90)
    missing, _ = shapes.before_pricing(rfq, R90, [])
    assert "other_lots" not in rfq


def test_book_only_the_first_shipment():
    lots = [{"destination": "RUH"}, {"destination": "GRU"}]
    assert booking_agent.lot_pick("Please go ahead and book the first shipment now; we will confirm the second "
                                  "shipment later.", lots) == 0
    assert booking_agent.lot_pick("Book the GRU one only please", lots) == 1
    assert booking_agent.lot_pick("Please book both.", lots) is None
    assert booking_agent.lot_pick("What is the transit time?", lots) is None


def test_a_cancellation_right_after_the_yes_stops_the_booking(monkeypatch):
    monkeypatch.setattr(booking_agent, "BOOK_GRACE_S", 0.01)
    yes = {"body": "Yes, please book it."}

    class Api:
        def events(self, session_id):
            return [{"kind": "mail_in", "data": yes},
                    {"kind": "mail_in", "data": {"body": "Our buyer withdrew the order, please don't go ahead, cancel it."}}]

    assert booking_agent._second_thoughts(yes, Api(), 1) == "a cancellation"

    class Quiet:
        def events(self, session_id):
            return [{"kind": "mail_in", "data": yes}]

    assert booking_agent._second_thoughts(yes, Quiet(), 1) is None
