"""LOT_ROUNDS (R150, R113): every extra lot of a multi-shipment RFQ gets its own carrier round (its lane's airlines,
its pickup zone's truckers, its own weight) in the same window as lot 1's, and those bids price it. Off by default."""
import threading
import time

import pytest

import rfq_agent
from bids import BidBoard
from inbox import FixtureMailbox
from test_rfq_agent import FakeApi, MAIL

FRANKFURT = {"address": "60413 Frankfurt am Main, Germany", "zone": None}
TLV = {"origin": "FRA", "destination": "TLV", "ask": "fastest", "pickup": FRANKFURT, "ready_date": "2026-11-24",
       "pieces": [{"count": 1, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 951}],
       "volume_m3": 4.67, "commodity": "machine parts", "dangerous_goods": False, "language": "en"}
R150 = {**TLV, "destination": "CAI", "volume_m3": 3.41,
        "pieces": [{"count": 6, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 92.17}],
        "other_lots": [TLV]}
BOREALIS = {"name": "Borealis", "email": "borealis@hackloop.mail", "kind": "airline", "serves": ["CAI"]}
FJORDLINE = {"name": "Fjordline", "email": "fjordline@hackloop.mail", "kind": "airline", "serves": ["TLV"]}
KESTREL = {"name": "Kestrel", "email": "kestrel@hackloop.mail", "kind": "airline", "serves": ["CAI", "TLV"]}
TAUNUS = {"name": "Taunusfracht", "email": "taunus@hackloop.mail", "kind": "trucker", "serves": ["60"]}
CARRIERS = [BOREALIS, FJORDLINE, KESTREL, TAUNUS]

MUNICH = {"address": "Munich, 80602, Germany", "zone": None}
DXB = {"origin": "MUC", "destination": "DXB", "ask": "fastest", "pickup": MUNICH, "ready_date": "2026-11-24",
       "pieces": [{"count": 11, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 112.636364}],
       "volume_m3": 5.27, "commodity": "coffee machines", "dangerous_goods": False, "language": "en"}
R113 = {**DXB, "destination": "RUH", "volume_m3": 4.8, "commodity": "coffee",
        "pieces": [{"count": 3, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 249.666667}],
        "other_lots": [DXB]}
JUNIPER = {"name": "Juniper Cargo Lines", "email": "juniper@hackloop.mail", "kind": "airline", "serves": ["RUH", "DXB"]}
BODENSEE = {"name": "Bodenseefracht", "email": "bodensee@hackloop.mail", "kind": "trucker", "serves": ["80"]}


class LotBox(FixtureMailbox):
    """Answers a bid request by (carrier address, destination in the subject): lot 1 and lot 2 get different bids."""

    def __init__(self, folder, board, answers):
        super().__init__(folder)
        self.board, self.answers = board, answers

    def send(self, to, subject, body):
        thread_id = super().send(to, subject, body)
        for (address, destination), text in self.answers.items():
            if address == to and subject.endswith("-" + destination):
                threading.Timer(0.05, self.board.deliver,
                                [{"thread_id": thread_id, "from": to, "body": text, "attachments": []}]).start()
        return thread_id


def bid(total, days=1, rate="R-1"):
    return f"Total: {total} EUR\nTransit: {days} days\nRate ID: {rate}"


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(rfq_agent, "LOT_ROUNDS", True)


def _rounds(tmp_path, rfq, carriers, answers, cutoff_s=0.6):
    """What _price_and_quote does: the lot rounds start, lot 1's round runs, then the lot rounds hand over."""
    board = BidBoard()
    box, api = LotBox(tmp_path, board, answers), TextApi({})
    mail = {**MAIL, "received_at": None}
    done = rfq_agent.lot_rounds(1, mail, rfq, carriers, box, api, board, cutoff_s)
    bids, _ = rfq_agent._carrier_round(1, mail, rfq, rfq_agent._targets(carriers, rfq), box, api, board, cutoff_s)
    return bids, done(), box, api


class TextApi(FakeApi):
    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.texts = [*getattr(self, "texts", []), text]
        return super().event(session_id, kind, text, data, cost)


class PriceApi:
    def __init__(self):
        self.asked = []

    def price(self, rfq, bids=None, fallback=False):
        self.asked.append((rfq["destination"], bids))
        total = sum(b["total"] for b in bids or [] if b.get("leg") == "air") or 3138.30
        pickup = next((b["total"] for b in bids or [] if b.get("leg") == "pickup"), 0)
        return {"chosen": {"carrier": "Fjordline", "currency": "EUR", "total": round(total + pickup, 2),
                           "transit_days": 2.125}, "why": "fastest"}

    def event(self, *a, **k):
        pass


def test_off_by_default_asks_lot_1_only(tmp_path):
    assert rfq_agent.LOT_ROUNDS is False
    bids, lots, box, _ = _rounds(tmp_path, R150, CARRIERS, {(TAUNUS["email"], "CAI"): bid(141.83)})
    assert lots == {} and {m["to"] for m in box.sent} == {BOREALIS["email"], KESTREL["email"], TAUNUS["email"]}
    assert all("Rate request FRA-CAI" == m["subject"] for m in box.sent)


def test_r150_lot_2_gets_its_own_round_and_its_own_bids(on, tmp_path):
    answers = {(BOREALIS["email"], "CAI"): bid(1919.11, 2), (KESTREL["email"], "CAI"): bid(1492.00, 3),
               (TAUNUS["email"], "CAI"): bid(141.83, 0.125, "TRK-1"),
               (FJORDLINE["email"], "TLV"): bid(2950.00, 2, "R-FJ"), (KESTREL["email"], "TLV"): bid(2390.00, 3),
               (TAUNUS["email"], "TLV"): bid(231.10, 0.125, "TRK-2")}
    bids, lots, box, api = _rounds(tmp_path, R150, CARRIERS, answers)
    tlv = [m for m in box.sent if m["subject"] == "Rate request FRA-TLV"]
    assert {m["to"] for m in tlv} == {FJORDLINE["email"], KESTREL["email"], TAUNUS["email"]}  # TLV's lane + zone 60
    assert all("951" in m["body"] for m in tlv)  # its own weight, not lot 1's 553 kg
    assert FJORDLINE["email"] not in {m["to"] for m in box.sent if m["subject"] == "Rate request FRA-CAI"}
    assert {b["carrier"]: b["total"] for b in bids} == {"Borealis": 1919.11, "Kestrel": 1492.0, "Taunusfracht": 141.83}
    assert lots[1]["destination"] == "TLV" and any(t.startswith("Shipment to TLV: Asked 3") for t in api.texts)
    assert {b["carrier"]: b["total"] for b in lots[1]["bids"]} == {"Fjordline": 2950.0, "Kestrel": 2390.0,
                                                                   "Taunusfracht": 231.1}

    priced = PriceApi()
    chosen = {"carrier": "Borealis", "currency": "EUR", "total": 2060.94, "transit_days": 2.125}
    lots_out, text = rfq_agent._multi_quote(1, MAIL, R150, chosen, bids, priced, lots)
    destination, used = priced.asked[0]
    assert destination == "TLV" and {b["carrier"] for b in used} == {"Fjordline", "Kestrel", "Taunusfracht"}
    assert next(b for b in used if b["leg"] == "pickup")["total"] == 231.1  # its own truck, not 141.83 scaled
    assert "TLV" in text and len(lots_out) == 2


def test_lot_2_without_its_own_truck_bid_keeps_lot_1s(on, tmp_path):
    answers = {(TAUNUS["email"], "CAI"): bid(141.83, 0.125), (FJORDLINE["email"], "TLV"): bid(2950.00, 2)}
    bids, lots, _, _ = _rounds(tmp_path, R150, CARRIERS, answers)
    priced = PriceApi()
    rfq_agent._multi_quote(1, MAIL, R150, {"carrier": "Kestrel", "currency": "EUR", "total": 1633.83,
                                           "transit_days": 3}, bids, priced, lots)
    used = priced.asked[0][1]
    assert {b["carrier"]: b["total"] for b in used} == {"Fjordline": 2950.0, "Taunusfracht": 141.83}


def test_r113_lot_2_is_priced_with_its_own_trucker_bid(on, tmp_path):
    answers = {(JUNIPER["email"], "RUH"): bid(2108.20), (BODENSEE["email"], "RUH"): bid(131.11, 1, "TRK-1"),
               (JUNIPER["email"], "DXB"): bid(3357.69), (BODENSEE["email"], "DXB"): bid(187.40, 1, "TRK-2")}
    bids, lots, box, _ = _rounds(tmp_path, R113, [JUNIPER, BODENSEE], answers)
    assert len([m for m in box.sent if m["to"] == BODENSEE["email"]]) == 2  # asked once per lot
    priced = PriceApi()
    rfq_agent._multi_quote(1, MAIL, R113, {"carrier": "Juniper Cargo Lines", "currency": "EUR", "total": 2239.31,
                                           "transit_days": 1.875}, bids, priced, lots)
    assert {b["carrier"]: b["total"] for b in priced.asked[0][1]} == {"Juniper Cargo Lines": 3357.69,
                                                                      "Bodenseefracht": 187.4}


def test_a_silent_lot_round_never_holds_the_quote(on, tmp_path, monkeypatch):
    # lot 2's trucker never answers: its round would wait for a pickup bid until PICKUP_DEADLINE_SECONDS, but it ends
    # with lot 1's round (lot 1 got everything it waits for)
    monkeypatch.setattr(rfq_agent, "PICKUP_DEADLINE_SECONDS", 60)
    answers = {(BOREALIS["email"], "CAI"): bid(1919.11, 2), (KESTREL["email"], "CAI"): bid(1492.00, 3),
               (TAUNUS["email"], "CAI"): bid(141.83, 0.125), (FJORDLINE["email"], "TLV"): bid(2950.00, 2)}
    start = time.time()
    _, lots, _, _ = _rounds(tmp_path, R150, CARRIERS, answers, cutoff_s=30)
    assert time.time() - start < 5  # lot 1's three carriers answered at once: no wait for lot 2's silent ones
    assert {b["carrier"] for b in lots[1]["bids"]} == {"Fjordline"}  # what lot 2 had by then is kept


def test_a_single_shipment_starts_no_lot_round(on, tmp_path):
    single = {k: v for k, v in R150.items() if k != "other_lots"}
    _, lots, box, _ = _rounds(tmp_path, single, CARRIERS, {(TAUNUS["email"], "CAI"): bid(141.83)})
    assert lots == {} and all(m["subject"] == "Rate request FRA-CAI" for m in box.sent)


def test_shared_truck_lot_rounds_ask_airlines_only(on, tmp_path, monkeypatch):
    """SHARED_PICKUP on (live): lot 2 keeps its share of the one truck, its round asks only its lane's airlines
    (sessions 155/156 would otherwise have priced lot 2 with a truck of its own)."""
    import shared_pickup
    monkeypatch.setattr(shared_pickup, "ON", True)
    answers = {(BOREALIS["email"], "CAI"): bid(1919.11, 2), (KESTREL["email"], "CAI"): bid(1492.00, 3),
               (TAUNUS["email"], "CAI"): bid(378.68, 0.125, "TRK-1"),
               (FJORDLINE["email"], "TLV"): bid(2950.00, 2, "R-FJ"), (TAUNUS["email"], "TLV"): bid(231.10, 0.125)}
    bids, lots, box, _ = _rounds(tmp_path, R150, CARRIERS, answers)
    tlv = {m["to"] for m in box.sent if m["subject"] == "Rate request FRA-TLV"}
    assert tlv == {FJORDLINE["email"], KESTREL["email"]}  # no trucker for lot 2
    assert len([m for m in box.sent if m["to"] == TAUNUS["email"]]) == 1  # the one truck, asked in lot 1's round
    assert all(b["leg"] != "pickup" for b in lots[1]["bids"])
