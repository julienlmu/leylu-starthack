from inbox import FixtureMailbox
from test_booking_tracking import BOOKING, FakeApi
from tracking_agent import handle_tracking
from tracking_match import best_match, is_date, signals

# The real tracking question of Sat 21 Nov, 16:18 (5U mailbox #923): no reference, only what the RFQ said.
QUESTION = {
    "id": 923, "thread_id": 923, "from": "tracking@hackloop.mail",
    "subject": "Status of our shipment 61018 to JFK, 1233 kg",
    "body": "Hello,\n\ncould you please tell me the current status of our shipment: Sonnberg Kaffeeroesterei GmbH, "
            "61018 to JFK, 1233 kg, ready on 2026-11-25? Where is it now?\n\nKind regards\nAnna Sonnberg\n"
            "Head of Purchasing and Logistics\nSonnberg Kaffeeroesterei GmbH",
}
# Its RFQ (#425): 6 pieces, 1233 kg gross, 10.78 cbm, pickup in 61018 Bad Homburg, ready 2026-11-25, booked.
SONNBERG = {
    "id": 31, "customer": "sonnberg-roesterei@hackloop.mail", "thread_id": 425, "stage": "booked",
    "rfq": {"origin": "FRA", "destination": "JFK", "ask": "fastest", "ready_date": "2026-11-25",
            "pickup": {"address": "61018 Bad Homburg, Germany", "zone": "61"},
            "pieces": [{"count": 6, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 205.5}],
            "volume_m3": 10.78},
    "quote": {"carrier": "Solace Air Cargo", "transit_days": 1, "total": 9876.0, "currency": "EUR"},
    "booking": {**BOOKING, "booking_reference": "BK-50NN8E8G", "airline": "Solace Air Cargo"},
}
# Same lane and day, other customer and weight: must not be picked.
OTHER = {
    "id": 32, "customer": "lindqvist-medtech@hackloop.mail", "thread_id": 500, "stage": "booked",
    "rfq": {"origin": "FRA", "destination": "JFK", "ready_date": "2026-11-25",
            "pickup": {"address": "51447 Bergisch Gladbach, Germany", "zone": "51"},
            "pieces": [{"count": 12, "weight_kg": 56.33}]},
    "booking": {**BOOKING, "booking_reference": "BK-OTHER123"},
}
TEXT = f"{QUESTION['subject']}\n{QUESTION['body']}"


def test_question_without_a_reference_finds_the_booked_shipment():
    assert signals(TEXT, SONNBERG) == {"weight": True, "customer": True, "destination": True,
                                       "postcode": True, "ready_date": True, "origin": False}
    assert best_match(TEXT, [OTHER, SONNBERG]) is SONNBERG


def test_unbooked_or_unclear_sessions_are_never_guessed():
    assert best_match(TEXT, [{**SONNBERG, "booking": None}]) is None
    twin = {**SONNBERG, "id": 33}
    assert best_match(TEXT, [SONNBERG, twin]) is None  # two shipments fit equally well
    assert best_match("Where is my shipment?", [SONNBERG, OTHER]) is None


def test_weights_are_read_in_any_notation():
    for written in ("1233 kg", "1,233 kg", "1.233 kg", "1233.0 kg"):
        assert signals(f"shipment to JFK, {written}", SONNBERG)["weight"], written
    assert not signals("shipment to JFK, 1300 kg", SONNBERG)["weight"]


def test_airport_instead_of_postcode_and_booked_weight_also_match():
    # Shape of #1212 ("Auer Maschinenbau GmbH, DUS to JFK, 1540 kg, ready on 2026-11-27") and of #1447 (679 kg = the
    # booked weight, not the RFQ's gross).
    auer = {"id": 40, "customer": "auer-maschinenbau@hackloop.mail", "thread_id": 700,
            "rfq": {"origin": "DUS", "destination": "JFK", "ready_date": "2026-11-27", "pickup": None,
                    "pieces": [{"count": 4, "weight_kg": 385.0}]},
            "booking": {**BOOKING, "booking_reference": "BK-AUER0001", "weight_kg": 1540.0}}
    text = ("Status of our shipment DUS to JFK, 1540 kg\ncould you please tell me the current status of our shipment: "
            "Auer Maschinenbau GmbH, DUS to JFK, 1540 kg, ready on 2026-11-27? Where is it now?")
    assert best_match(text, [SONNBERG, OTHER, auer]) is auer
    booked_weight = {**auer, "rfq": {**auer["rfq"], "pieces": [{"count": 4, "weight_kg": 380.0}]},
                     "booking": {**auer["booking"], "weight_kg": 1540.0}}
    assert signals(text, booked_weight)["weight"]


def test_a_date_is_not_a_reference():
    assert is_date("2026-11-25") and not is_date("BK-50NN8E8G") and not is_date("PO-4711")


def test_tracking_agent_answers_the_real_question_from_the_crm(tmp_path):
    box, api = FixtureMailbox(tmp_path), FakeApi([OTHER, SONNBERG])
    handle_tracking(QUESTION, box, api)
    [answer] = box.sent
    assert answer["thread_id"] == 923
    assert "BK-50NN8E8G" in answer["body"] and "Solace Air Cargo" in answer["body"]
    assert "2026-11-25" not in api.lookups  # the date was not looked up as a reference
    assert api.events == ["tracking_answer"]


AUER = {**OTHER, "id": 33, "customer": "auer-maschinenbau@hackloop.mail",
        "rfq": {"origin": "MUC", "destination": "JFK", "ready_date": "2026-11-25",
                "pickup": {"address": "80331 München, Germany", "zone": "80"}, "pieces": [{"count": 1, "weight_kg": 500}]},
        "booking": {**BOOKING, "booking_reference": "BK-AUER0001"}}
SMALL = {**OTHER, "id": 34, "customer": "kraus-optik@hackloop.mail",
         "rfq": {"origin": "FRA", "destination": "ORD", "ready_date": "2026-11-25", "pickup": None,
                 "pieces": [{"count": 1, "weight_kg": 25}]},
         "booking": {**BOOKING, "booking_reference": "BK-KRAUS001"}}


def test_a_question_never_gets_another_customers_shipment():
    # Same weight and destination, but a different ready date: Huber is not Auer.
    assert best_match("Huber GmbH, 80331 to JFK, 500 kg, ready on 2026-11-27", [AUER]) is None
    # The "25" in a date, a postcode or a year is not a weight: a 900 kg question must not match a 25 kg booking.
    assert best_match("Kraus Optik, FRA to ORD, 900 kg, ready on 2026-11-25", [SMALL]) is None
    # "auer" inside "Sauerland" is not the customer Auer, and an identity alone names no shipment.
    assert best_match("Sauerland Metall, 80331 to JFK", [AUER]) is None
    # The same customer's other, unbooked shipment (other weight) doesn't get this booking's status.
    assert best_match("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 400 kg, ready on 2026-11-25", [SONNBERG]) is None
    # The real question still matches, written with a thousands separator too.
    assert best_match(TEXT.replace("1233 kg", "1,233 kg"), [AUER, SMALL, SONNBERG]) is SONNBERG


def test_an_unknown_bk_reference_is_not_guessed_from_the_details(tmp_path):
    box, api = FixtureMailbox(tmp_path), FakeApi([SONNBERG])
    handle_tracking({**QUESTION, "body": QUESTION["body"] + "\nOur booking is BK-ZZZZZZZZ."}, box, api)
    assert "BK-50NN8E8G" not in box.sent[0]["body"] and api.events == []
