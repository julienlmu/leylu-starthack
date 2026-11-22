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


def test_after_booking_the_first_the_quotes_go_again_with_their_status():
    lots = [{"destination": "RUH", "rfq": {"pieces": [{"count": 6, "weight_kg": 98.5}], "commodity": "sports equipment"},
             "option": {"carrier": "Tamarind Airways", "currency": "EUR", "total": 2059.28, "transit_days": 1.4}},
            {"destination": "GRU", "rfq": {"pieces": [{"count": 6, "weight_kg": 222.5}], "commodity": "machine parts"},
             "option": {"carrier": "Ibisair Cargo", "currency": "EUR", "total": 5383.54, "transit_days": 3.4}}]
    session = {"rfq": {"destination": "RUH", "contact_name": "Deniz Yilmaz", "pickup": {"address": "20674 Hamburg"}},
               "booking": {"status": "booked", "pending_email": None, "booking_reference": None, "airline": "Tamarind Airways"}}
    ask = ("Thanks! Please send the RUH booking reference once it's confirmed, and keep GRU on hold. Could you also send "
           "the separate all-in quotes in EUR for RUH and GRU in one reply?")
    assert booking_agent.RESEND.search(ask)
    text = booking_agent.lots_status_text(session, lots)
    assert "EUR 2,059.28" in text and "EUR 5,383.54" in text and "On hold" in text and "Booked" in text


def test_r91_r92_insurance_premium_is_added_once():
    """#231 (insurance.add in Backend.price) is the one insurance path: the premium is in the all-in exactly once."""
    import backend
    import insurance
    for text, premium in (("We also need cargo insurance inside your all-in price: the goods are worth 81000 EUR, cover "
                           "is 110 % of the value and the premium rate is 0.30 % (our frame agreement).", 267.30),
                          ("Please include cargo insurance in the all-in price, on the terms of our frame agreement: "
                           "goods value 22000 EUR, insured at 110 % of that value, premium rate 0.40 %.", 96.80)):
        rfq = {"insurance": insurance.terms(text)}
        result = {"chosen": {"carrier": "X", "currency": "EUR", "total": 1000.0, "total_eur": 1000.0},
                  "options": [{"carrier": "X", "currency": "EUR", "total": 1000.0, "total_eur": 1000.0}]}
        out = insurance.add(insurance.add(result, rfq), rfq)  # twice: still one premium
        assert round(out["chosen"]["total"], 2) == round(1000 + premium, 2), text
    assert not hasattr(backend, "with_insurance")  # the quick patch is gone: no second path
