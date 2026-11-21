import re
import threading
import time

import extract as extract_mod
import rfq_agent
from bids import BidBoard
from extract import to_rfq
from inbox import FixtureMailbox

RAW = {
    "origin": "MUC", "destination": "JFK", "ask": None, "pickup_address": "Industriestr. 12, 85748 Garching",
    "ready_date": "2026-11-23",
    "pieces": [{"count": 2, "length": 48, "width": 40, "height": 40, "weight": 440, "weight_is_total": True}],
    "dim_unit": "in", "weight_unit": "lb", "volume_unit": "m3", "volume": None, "commodity": "machine parts",
    "dangerous_goods": False, "customer_reference": "PO-4711", "language": "de",
}
OPTION = {"source": "sheet", "carrier": "SkyAir", "rate_id": None, "currency": "EUR", "total": 1856.0,
          "transit_days": 2, "valid_until": "2026-11-28", "chargeable_weight_kg": 480, "breakdown": []}
MAIL = {"id": "m1", "thread_id": "t1", "from": "buyer@customer.example", "subject": "RFQ MUC-JFK",
        "body": "2 crates, 48 x 40 x 40 in, 440 lb in total, pickup Industriestr. 12, 85748 Garching, ready 2026-11-23."}
CARRIERS = [{"name": "SkyAir", "email": "bids@skyair.example", "kind": "airline", "serves": ["JFK"]},
            {"name": "CloudCargo", "email": "rates@cloud.example", "kind": "airline", "serves": ["*"]},
            {"name": "Huber Transporte", "email": "dispo@huber.example", "kind": "trucker", "serves": ["85"]}]


class FakeApi:
    def __init__(self, price_result):
        self.price_result, self.updates, self.events, self.bids = price_result, [], [], None
        self.data, self.received_at = {}, None

    def create_session(self, customer, thread_id, received_at=None):
        self.received_at = received_at
        return 1

    def session(self, session_id):
        return {"paused": False, "needs_human": "needs_human" in self.events, "quote": None}

    def update(self, session_id, **fields):
        self.updates.append(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append(kind)
        self.data[kind] = data

    def price(self, rfq, bids=None, fallback=False):
        self.bids, self.fallback = bids, fallback
        if fallback and getattr(self, "fallback_result", None):
            return self.fallback_result
        return self.price_result


def test_to_rfq_converts_units_and_total_weight():
    rfq, missing = to_rfq(RAW)
    assert rfq["pieces"] == [{"count": 2, "length_cm": 121.9, "width_cm": 101.6, "height_cm": 101.6, "weight_kg": 99.790321}]
    assert rfq["ask"] == "cheapest"
    assert rfq["pickup"] == {"address": "Industriestr. 12, 85748 Garching", "zone": None}
    assert missing == []


def test_door_to_port_origin_comes_from_the_pickup_zone():
    raw = {**RAW, "origin": None, "pickup_address": "51447 Bergisch Gladbach, Germany"}
    rfq, missing = to_rfq(raw)
    assert rfq["origin"] == "CGN" and "origin" not in missing
    raw = {**RAW, "origin": "MUC", "pickup_address": "Hauptstr. 1, 60311 Frankfurt"}
    assert to_rfq(raw)[0]["origin"] == "FRA"  # the pickup decides the airport


def test_to_rfq_lists_what_is_missing():
    raw = {**RAW, "origin": None, "pickup_address": None, "pieces": [{"count": 1, "length": None, "width": None, "height": None,
                                               "weight": None, "weight_is_total": False}]}
    assert to_rfq(raw)[1] == ["origin", "weight", "dimensions or volume"]


def test_handle_rfq_quotes_one_total_in_the_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION, "why": "cheapest"})
    rfq_agent.handle_rfq(MAIL, box, api)
    [sent] = box.sent
    assert sent["thread_id"] == "t1"
    assert re.findall(r"\d[\d,]*\.\d{2}", sent["body"]) == ["1,856.00"]
    assert "EUR 1,856.00" in sent["body"]
    assert api.events == ["mail_in", "routed", "extracted", "priced", "quote_sent"]
    assert api.updates[-1]["stage"] == "quoted"


def test_mail_events_carry_the_mails_and_the_session_gets_the_arrival_time(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION, "why": "cheapest"})
    mail = {**MAIL, "to": "leylu@hackloop.mail", "received_at": "2026-11-21T15:00:00+00:00"}
    rfq_agent.handle_rfq(mail, box, api)
    assert api.received_at == "2026-11-21T15:00:00+00:00"  # the UI's response time counts from here
    assert api.data["mail_in"] == {"from": "buyer@customer.example", "to": "leylu@hackloop.mail",
                                   "subject": "RFQ MUC-JFK",
        "body": "2 crates, 48 x 40 x 40 in, 440 lb in total, pickup Industriestr. 12, 85748 Garching, ready 2026-11-23."}
    quote = api.data["quote_sent"]
    assert (quote["from"], quote["to"], quote["subject"]) == ("leylu@hackloop.mail", "buyer@customer.example",
                                                              "Re: RFQ MUC-JFK")
    assert quote["body"] == box.sent[-1]["body"] and quote["option"] == OPTION


def test_handle_rfq_hands_over_without_mailing(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [], "chosen": None, "why": ""})
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    rfq_agent.handle_rfq(MAIL, box, api)
    assert box.sent == []  # the fallback found no price either
    assert api.events[-1] == "needs_human"


def test_handle_rfq_asks_carriers_and_prices_with_their_bids(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))  # RAW wants pickup → trucker asked too
    box, api, board = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION}), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(MAIL, box, api, board, CARRIERS, 5))
    worker.start()
    give_up = time.time() + 2
    while len(box.sent) < 3 and time.time() < give_up:
        time.sleep(0.01)
    assert [m["to"] for m in box.sent] == ["bids@skyair.example", "rates@cloud.example", "dispo@huber.example"]
    for request in list(box.sent):
        board.deliver({"thread_id": request["thread_id"], "body": "Total: 900.00 EUR\nTransit: 2 days\nRate ID: R-1"})
    worker.join(timeout=5)
    assert [(b["carrier"], b["leg"]) for b in api.bids] == [
        ("SkyAir", "air"), ("CloudCargo", "air"), ("Huber Transporte", "pickup")]
    assert box.sent[-1]["thread_id"] == "t1"  # the quote goes into the customer's thread
    assert "quote_sent" in api.events


def test_handle_rfq_quotes_at_the_cutoff_when_carriers_stay_silent(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    started = time.time()
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), CARRIERS[:1], cutoff_s=0.2)
    assert time.time() - started < 2
    assert api.bids == []
    assert box.sent[-1]["thread_id"] == "t1"


def test_a_carrier_whose_send_fails_is_skipped_and_the_rfq_still_quotes(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))

    class PickyBox(FixtureMailbox):
        def send(self, to, subject, body):
            if to == "bids@skyair.example":
                raise RuntimeError("422 recipient not allowed")
            return super().send(to, subject, body)

    monkeypatch.setattr(rfq_agent, "PICKUP_DEADLINE_SECONDS", 0.4)  # the trucker never answers in this test
    box, api = PickyBox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), CARRIERS, cutoff_s=0.2)
    assert [m["to"] for m in box.sent][:2] == ["rates@cloud.example", "dispo@huber.example"]
    assert box.sent[-1]["thread_id"] == "t1"  # the quote still went out
    assert "quote_sent" in api.events and "error" not in api.events


def test_orchestrator_keeps_the_cheap_read_when_it_passes_the_checks(monkeypatch):
    calls = []
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model="gpt-6-luna": calls.append(model) or (RAW, 0.0001))
    read = extract_mod.read_request(MAIL)
    assert calls == ["gpt-6-luna"] and read["escalated"] is None and read["cost"] == 0.0001


def test_orchestrator_escalates_an_incomplete_read_to_the_stronger_model(monkeypatch):
    weak = {**RAW, "pieces": [{**RAW["pieces"][0], "weight": None}]}  # the cheap model missed the weight
    calls = []

    def fake(mail, model="gpt-6-luna"):
        calls.append(model)
        return (weak, 0.0001) if model == "gpt-6-luna" else (RAW, 0.001)

    monkeypatch.setattr(extract_mod, "extract", fake)
    read = extract_mod.read_request(MAIL)
    assert calls == ["gpt-6-luna", "gpt-6.1-terra"]
    assert read["missing"] == [] and read["model"] == "gpt-6.1-terra" and read["cost"] == 0.0011
    assert read["escalated"] == ["missing weight"]


def test_orchestrator_questions_dimensions_that_disagree_with_the_volume_and_survives_a_failing_escalation(monkeypatch):
    odd = {**RAW, "volume": 9.9}  # 2 x 48x40x40 in = 2.0 m3, not 9.9
    def fake(mail, model="gpt-6-luna"):
        if model != "gpt-6-luna":
            raise TimeoutError("gateway")
        return odd, 0.0001
    monkeypatch.setattr(extract_mod, "extract", fake)
    read = extract_mod.read_request(MAIL)
    assert read["model"] == "gpt-6-luna" and read["rfq"]["volume_m3"] == 9.9
    assert any("m3 but the mail says 9.9" in r for r in read["escalated"])
    assert read["escalated"][-1] == "escalation failed: TimeoutError"


def test_door_to_port_waits_past_the_cutoff_for_the_first_trucker(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))  # RAW wants pickup in zone 85
    monkeypatch.setattr(rfq_agent, "PICKUP_DEADLINE_SECONDS", 3)
    box, api, board = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION}), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(MAIL, box, api, board, CARRIERS, 0.2))
    worker.start()
    give_up = time.time() + 2
    while len(box.sent) < 3 and time.time() < give_up:
        time.sleep(0.01)
    time.sleep(0.6)  # well past the 0.2 s cut-off: an airline-only RFQ would have quoted already
    trucker = next(m for m in box.sent if m["to"] == "dispo@huber.example")
    board.deliver({"thread_id": trucker["thread_id"], "body": "Total: 119.01 EUR\nTransit: 30 hours\nRate ID: TRK-1"})
    worker.join(timeout=5)
    assert [b["leg"] for b in api.bids] == ["pickup"]  # the late trucker bid made it into pricing
    assert box.sent[-1]["thread_id"] == "t1"



def test_volumes_per_lot_are_summed():
    lot = {"count": 1, "length": None, "width": None, "height": None, "weight_is_total": True}
    raw = {**RAW, "pickup_address": None, "volume": None,
           "pieces": [{**lot, "weight": 618, "volume": 0.74}, {**lot, "weight": 380, "volume": 1.65}]}
    rfq, missing = to_rfq(raw)
    assert rfq["volume_m3"] == 2.39 and missing == []


def test_units_are_converted_by_code_tonnes_cubic_feet_and_per_piece_volume():
    line = {"count": 15, "length": None, "width": None, "height": None, "weight": 18, "weight_is_total": False,
            "volume": 0.42, "volume_is_total": False}
    rfq, missing = to_rfq({**RAW, "pickup_address": None, "weight_unit": "kg", "pieces": [line]})
    assert rfq["volume_m3"] == 6.3 and missing == []  # 15 cartons × 0.42 cbm each, not 0.42 in total
    rfq, _ = to_rfq({**RAW, "pickup_address": None, "weight_unit": "t", "volume_unit": "ft3", "volume": 95,
                     "pieces": [{**line, "count": 9, "weight": 2.4, "weight_is_total": True, "volume": None}]})
    assert round(9 * rfq["pieces"][0]["weight_kg"]) == 2400 and rfq["volume_m3"] == 2.6901


def test_a_misread_unit_is_caught_by_the_density_and_goes_to_a_person_if_the_re_read_agrees(monkeypatch):
    tonnes_as_kg = {**RAW, "pickup_address": None, "weight_unit": "kg", "volume": 14,
                    "pieces": [{"count": 9, "length": None, "width": None, "height": None, "weight": 2.4,
                                "weight_is_total": True}]}
    mail = {**MAIL, "body": "9 pieces, gross weight 2.4 t, 14 cbm, ready 2026-11-23"}
    monkeypatch.setattr(extract_mod, "extract", lambda m, model="gpt-6-luna": (tonnes_as_kg, 0.0001))
    read = extract_mod.read_request(mail)
    assert any("implausible density" in r for r in read["escalated"])
    assert any("implausible density" in m for m in read["missing"])  # never quoted from 2.4 kg


def test_numbers_the_mail_does_not_contain_are_questioned():
    assert {1233.0, 6.8, 1150.0, 1250.5} <= extract_mod._mail_numbers("1.233 kg, 6,8 m³, 1,150 lbs, je 1.250,5 kg")
    converted = {**RAW, "volume": 2.69, "pieces": [{**RAW["pieces"][0], "length": None}]}
    found = extract_mod.ungrounded(converted, {"body": "2 crates, 40 x 40 in, 440 lb, 95 cu ft"})
    assert found == ["2.69 is not in the mail"]
    assert extract_mod.ungrounded(RAW, {**MAIL, "received_at": "2026-11-25T10:00:00Z"}) == [
        "ready date 2026-11-23 is before the mail (2026-11-25)"]


def test_a_total_line_counted_as_a_lot_is_questioned():
    rfq, _ = to_rfq({**RAW, "pickup_address": None, "volume": 5.12, "pieces": [
        {"count": 4, "length": None, "width": None, "height": None, "weight": 210, "weight_is_total": False},
        {"count": 2, "length": None, "width": None, "height": None, "weight": 95, "weight_is_total": False},
        {"count": 6, "length": None, "width": None, "height": None, "weight": 1030, "weight_is_total": True}]})
    assert "one piece line is the total of the others (counted twice)" in extract_mod.doubts(rfq)


def test_pickup_city_without_a_postcode_gives_the_zone_and_the_airport():
    assert extract_mod.city_zone("our plant in Ingolstadt") == "85"
    assert extract_mod.city_zone("Werk München-Süd") == "80" and extract_mod.city_zone("Köln-Porz") == "50"
    assert extract_mod.city_zone("somewhere in Paris") is None
    rfq, missing = to_rfq({**RAW, "origin": None, "pickup_address": "our plant in Ingolstadt"})
    assert rfq["pickup"]["zone"] == "85" and rfq["origin"] == "MUC" and missing == []


def test_total_weight_split_over_pieces_adds_up_again():
    lot = {"count": 12, "length": None, "width": None, "height": None, "weight": 1228, "weight_is_total": True,
           "volume": None}
    rfq, _ = to_rfq({**RAW, "weight_unit": "kg", "pickup_address": None, "volume": 5.37, "pieces": [lot]})
    assert round(sum(p["count"] * p["weight_kg"] for p in rfq["pieces"]), 2) == 1228.0  # 102.33 × 12 = 1227.96 booked short



def test_mixed_lots_volume_and_dimensions_add_up():
    base = {"weight_is_total": False, "volume": None}
    raw = {**RAW, "pickup_address": None, "volume": None, "dim_unit": "cm", "weight_unit": "kg", "pieces": [
        {**base, "count": 4, "length": None, "width": None, "height": None, "weight": 730, "weight_is_total": True,
         "volume": 1.68},
        {**base, "count": 4, "length": 110, "width": 110, "height": 52, "weight": 60},
        {**base, "count": 5, "length": 120, "width": 100, "height": 8, "weight": 40}]}
    rfq, missing = to_rfq(raw)
    assert round(rfq["volume_m3"], 2) == 4.68 and missing == []



def test_no_price_then_nobody_steps_in_sends_a_fallback_quote(monkeypatch, tmp_path):
    import rfq_agent
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(rfq_agent, "read_request", lambda mail: {"rfq": to_rfq(RAW)[0], "missing": [], "cost": 0.0001,
                                                                 "model": "m", "escalated": None})
    api = FakeApi({"options": [], "chosen": None, "why": "door-to-port but no trucker bid"})
    api.fallback_result = {"options": [OPTION], "chosen": OPTION, "why": "pickup from an earlier bid"}
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert api.fallback is True and "needs_human" in api.events and api.events[-1] == "quote_sent"
    assert len(box.sent) == 1 and "EUR" in box.sent[0]["body"]


def test_no_second_quote_when_a_person_quoted_by_hand_during_the_carrier_round(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))

    class QuotedByHand(FakeApi):
        def session(self, session_id):
            return {"paused": False, "quote": {"total": 1856.0, "by": "person"}}

    box = FixtureMailbox(tmp_path)
    api = QuotedByHand({"options": [OPTION], "chosen": OPTION})
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0.1)
    assert "priced" in api.events  # it got all the way to the quote…
    assert box.sent == [] and "quote_sent" not in api.events  # …and held it


def test_a_resumed_rfq_continues_its_session_and_gets_its_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))

    class NoNewSession(FakeApi):
        def create_session(self, *args, **kwargs):
            raise AssertionError("a resumed RFQ must not open a second session")

    box, api = FixtureMailbox(tmp_path), NoNewSession({"options": [OPTION], "chosen": OPTION})
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0.1, session_id=42)
    assert "quote_sent" in api.events and box.sent[-1]["thread_id"] == "t1"


def test_a_trucker_asking_for_the_postcode_gets_it_and_its_later_bid_is_priced(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))  # pickup in 85748 Garching
    monkeypatch.setattr(rfq_agent, "PICKUP_DEADLINE_SECONDS", 3)
    box, api, board = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION}), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(MAIL, box, api, board, CARRIERS, 0.2))
    worker.start()
    give_up = time.time() + 2
    while len(box.sent) < 3 and time.time() < give_up:
        time.sleep(0.01)
    trucker = next(m for m in box.sent if m["to"] == "dispo@huber.example")
    assert "85748" in trucker["body"]  # the bid request names the postcode up front
    board.deliver({"thread_id": trucker["thread_id"], "from": "dispo@huber.example", "subject": "Re: Rate request",
                   "body": "Hello,\n\nTo quote we need:\n- the pickup postcode\n\nPlease reply in this thread."})
    give_up = time.time() + 2
    while not any("Pickup postcode: 85748" in m["body"] for m in box.sent) and time.time() < give_up:
        time.sleep(0.01)
    board.deliver({"thread_id": trucker["thread_id"], "body": "Total: 119.01 EUR\nTransit: 30 hours\nRate ID: TRK-1"})
    worker.join(timeout=5)
    assert [b["leg"] for b in api.bids] == ["pickup"] and box.sent[-1]["thread_id"] == "t1"


def _read_as(missing):
    return lambda mail: {"rfq": to_rfq(RAW)[0], "missing": missing, "cost": 0.0001, "model": "m", "escalated": None}


def test_a_packing_list_weight_fills_a_mail_that_gives_none():
    rfq = {"pieces": [{"count": 3, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": None}],
           "volume_m3": 2.65}
    notes = rfq_agent._use_packing_list_totals(rfq, ["Total pieces: 3\nTotal gross weight (kg): | 715\nTotal volume (cbm): | 2.65"])
    assert round(sum(p["count"] * p["weight_kg"] for p in rfq["pieces"]), 6) == 715
    assert notes == ["No weight in the mail: using the packing list's 715 kg"]
    empty = {"pieces": [], "volume_m3": None}
    rfq_agent._use_packing_list_totals(empty, ["Total gross weight (kg): 120"])
    assert empty["pieces"][0]["weight_kg"] == 120


def test_odd_numbers_are_quoted_as_read_when_nobody_steps_in(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(rfq_agent, "read_request", _read_as(["implausible density 5 kg/m3"]))
    api, box = FakeApi({"options": [OPTION], "chosen": OPTION}), FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert api.events.index("needs_human") < api.events.index("quote_sent")  # a person was told first
    assert len(box.sent) == 1 and api.updates[-1]["needs_human"] is False


def test_odd_numbers_wait_for_the_person_who_stepped_in(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(rfq_agent, "read_request", _read_as(["implausible density 5 kg/m3"]))

    class Paused(FakeApi):
        def session(self, session_id):
            return {"paused": True, "needs_human": True, "quote": None}

    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, Paused({"options": [OPTION], "chosen": OPTION}), BidBoard(), [], cutoff_s=0)
    assert box.sent == []


def test_a_crash_after_reading_the_request_still_sends_the_fallback_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(rfq_agent, "read_request", _read_as([]))

    class BackendHiccup(FakeApi):
        def price(self, rfq, bids=None, fallback=False):
            if not fallback:
                raise RuntimeError("502 Bad Gateway")
            return {"options": [OPTION], "chosen": OPTION, "why": "fallback"}

        def session(self, session_id):
            return {"paused": False, "needs_human": True, "quote": None}

    api, box = BackendHiccup({}), FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert "error" in api.events and api.events[-1] == "quote_sent" and len(box.sent) == 1


def test_a_crash_after_the_quote_went_out_sends_no_second_one(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(rfq_agent, "read_request", _read_as([]))

    class StoreFails(FakeApi):
        def update(self, session_id, **fields):
            if "quote" in fields and not fields.get("quote", {}).get("fallback"):
                raise RuntimeError("backend down")
            super().update(session_id, **fields)

        def session(self, session_id):
            return {"paused": False, "needs_human": True, "quote": None}

    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, StoreFails({"options": [OPTION], "chosen": OPTION}), BidBoard(), [], cutoff_s=0)
    assert len(box.sent) == 1


def test_fallback_after_restart_runs_the_fallback_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    api, box = FakeApi({"options": [OPTION], "chosen": OPTION}), FixtureMailbox(tmp_path)
    api.events.append("needs_human")  # handed over before the restart
    session = {"id": 1, "rfq": to_rfq(RAW)[0], "bids": []}
    rfq_agent.fallback_after_restart(session, {**MAIL, "received_at": None}, box, api)
    assert api.fallback is True and api.events[-1] == "quote_sent" and len(box.sent) == 1
