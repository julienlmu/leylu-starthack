"""SHARED_PICKUP (R113): two shipments from one site on one day share one truck: the truckers price all lots together
and each lot carries its share of that truck by chargeable weight. Off (default): exactly as before."""
import pytest

import rfq_agent
import shared_pickup
from bids import BidBoard
from test_rfq_agent import FakeApi, MAIL
from test_traps2_bids import DeliveringBox

PICKUP = {"address": "Munich, 80602, Germany", "zone": None}
LOT2 = {"origin": "MUC", "destination": "DXB", "ask": "fastest", "pickup": PICKUP, "ready_date": "2026-11-24",
        "pieces": [{"count": 11, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 112.636364}],
        "volume_m3": 5.27, "commodity": "coffee machines", "dangerous_goods": False, "language": "en"}
R113 = {**LOT2, "destination": "RUH", "volume_m3": 4.8, "commodity": "coffee",
        "pieces": [{"count": 3, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 249.666667}],
        "other_lots": [LOT2]}
TRUCK = {"name": "Bodenseefracht", "email": "bodenseefracht@hackloop.mail", "kind": "trucker", "serves": ["80"]}
AIR = {"name": "Juniper Cargo Lines", "email": "juniper@hackloop.mail", "kind": "airline", "serves": ["RUH"]}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(shared_pickup, "ON", True)


def test_off_by_default_changes_nothing():
    assert shared_pickup.ON is False and shared_pickup.combined(R113) is None
    bid = {"leg": "pickup", "carrier": "Bodenseefracht", "total": 131.11}
    assert shared_pickup.lot_bid(bid, 0.6) is bid


def test_r113_one_truck_for_both_lots(on):
    truck = shared_pickup.combined(R113)
    assert "other_lots" not in truck and len(truck["pieces"]) == 2 and truck["volume_m3"] == pytest.approx(10.07)
    assert rfq_agent.chargeable_kg(truck) == pytest.approx(1988, abs=0.5)  # 749 + 1,239 kg, more than 10.07 cbm × 167
    one, two = shared_pickup.shares(R113)
    assert one == pytest.approx(801.6 / 2040.6, abs=1e-4) and two == pytest.approx(1239 / 2040.6, abs=1e-4)


def test_shares_add_up_to_the_truck_price_once(on):
    bid = {"leg": "pickup", "carrier": "Bodenseefracht", "total": 309.07, "truck_total": 309.07, "truck_kg": 1988}
    parts = [shared_pickup.lot_bid(bid, s)["total"] for s in shared_pickup.shares(R113)]
    assert sum(parts) == pytest.approx(309.07, abs=0.02) and parts[0] < parts[1]
    air = {"leg": "air", "carrier": "Juniper Cargo Lines", "total": 2108.2}
    assert shared_pickup.lot_bid(air, 0.4) is air  # air bids are never split


@pytest.mark.parametrize("change", [{"pickup": {"address": "Augsburg, 86150, Germany", "zone": None}},
                                    {"ready_date": "2026-11-25"}, {"origin": "FRA"}])
def test_another_site_day_or_airport_is_two_trucks(on, change):
    assert shared_pickup.combined({**R113, "other_lots": [{**LOT2, **change}]}) is None


def test_a_single_shipment_is_never_touched(on):
    single = {k: v for k, v in R113.items() if k != "other_lots"}
    assert shared_pickup.combined(single) is None


def _round(tmp_path, answers):
    board = BidBoard()
    box, api = DeliveringBox(tmp_path, board, answers), FakeApi({})
    got, _ = rfq_agent._carrier_round(1, {**MAIL, "received_at": None}, R113, [TRUCK, AIR], box, api, board, 0.5)
    return got, box


def test_the_trucker_is_asked_for_the_whole_truck_and_lot_1_carries_its_share(on, tmp_path):
    got, box = _round(tmp_path, {TRUCK["email"]: ["Total: 309.07 EUR\nTransit: 1 day\nRate ID: TRK-1"],
                                 AIR["email"]: ["Total: 2108.20 EUR\nTransit: 1 day\nRate ID: R-1"]})
    sent = {m["to"]: m["body"] for m in box.sent}
    assert "3 pcs" in sent[TRUCK["email"]] and "11 pcs" in sent[TRUCK["email"]]  # both lots on the truck
    assert "11 pcs" not in sent[AIR["email"]]  # the airline still prices lot 1's lane only
    truck = next(b for b in got if b["leg"] == "pickup")
    assert truck["truck_total"] == 309.07 and truck["total"] == pytest.approx(309.07 * 801.6 / 2040.6, abs=0.01)
    assert next(b for b in got if b["leg"] == "air")["total"] == 2108.2


def test_off_the_trucker_gets_lot_1_only_as_before(tmp_path):
    got, box = _round(tmp_path, {TRUCK["email"]: ["Total: 131.11 EUR\nTransit: 1 day\nRate ID: TRK-1"]})
    assert "11 pcs" not in {m["to"]: m["body"] for m in box.sent}[TRUCK["email"]]
    assert next(b for b in got if b["leg"] == "pickup") == {
        "source": "carrier_bid", "leg": "pickup", "carrier": "Bodenseefracht", "rate_id": "TRK-1", "currency": "EUR",
        "total": 131.11, "transit_days": 1.0}


def test_lot_2_is_priced_with_its_share(on):
    asked = []

    class Api:
        def price(self, rfq, bids=None, fallback=False):
            asked.append(bids)
            return {"chosen": {"carrier": "Lumen Air Cargo", "currency": "EUR", "total": 3357.69 + bids[0]["total"],
                               "transit_days": 1.875}, "why": "fastest"}

        def event(self, *a, **k):
            pass

    truck = {"source": "carrier_bid", "leg": "pickup", "carrier": "Bodenseefracht", "total": 121.4,
             "truck_total": 309.07, "truck_kg": 1988.0}
    chosen = {"carrier": "Juniper Cargo Lines", "currency": "EUR", "total": 2229.6, "transit_days": 1.875}
    lots, text = rfq_agent._multi_quote(1, MAIL, R113, chosen, [truck], Api())
    assert asked[0][0]["total"] == pytest.approx(309.07 * 1239 / 2040.6, abs=0.01)
    assert "one truck from Munich, 80602, Germany for all of them" in text and "EUR 3,545.35" in text
