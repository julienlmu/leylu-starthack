"""LOT_PICKUP_LINE (R185, session 193): lot 2 without its own trucker bid is priced with a pickup for its own weight
(the backend's fallback estimate), never with lot 1's truck bid. Off by default."""
import pytest

import rfq_agent
from test_lot_rounds import MAIL

DUS = {"address": "40053 (Duesseldorf), Germany", "zone": None}
BOM = {"origin": "DUS", "destination": "BOM", "ask": "fastest", "pickup": DUS, "ready_date": "2026-11-27",
       "pieces": [{"count": 10, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 62.0}],
       "volume_m3": 2.75, "commodity": "machine parts", "dangerous_goods": False, "language": "en"}
R185 = {**BOM, "destination": "YYZ", "volume_m3": 11.33, "commodity": "precision instruments",
        "pieces": [{"count": 12, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 133.666667}],
        "other_lots": [BOM]}
DOMBLICK = {"source": "carrier_bid", "leg": "pickup", "carrier": "Domblick Kurierdienst", "rate_id": "TRK-17847",
            "currency": "EUR", "total": 379.97, "transit_days": 0.1667}
JUNIPER = {"source": "carrier_bid", "leg": "air", "carrier": "Juniper Cargo Lines", "currency": "EUR",
           "total": 4805.96, "transit_days": 2}
YYZ_QUOTE = {"carrier": "Juniper Cargo Lines", "currency": "EUR", "total": 5185.93, "transit_days": 2.17}


class LineApi:
    """fallback=True → the backend's estimate for this lot's weight (Domblick's line: ~214.60 at 620 kg)."""

    def __init__(self, estimate=214.60):
        self.asked, self.estimate = [], estimate

    def price(self, rfq, bids=None, fallback=False):
        self.asked.append((bids, fallback))
        pickup = next((b for b in bids or [] if b.get("leg") == "pickup"), None)
        if pickup is None and fallback and self.estimate is not None:
            pickup = {**DOMBLICK, "rate_id": None, "total": self.estimate}
        total = 2213.40 + (pickup["total"] if pickup else 0)
        return {"chosen": {"carrier": "Fjordline Air Cargo", "currency": "EUR", "total": round(total, 2),
                           "transit_days": 2.17, "pickup": pickup}, "why": "fastest"}

    def event(self, *a, **k):
        pass


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(rfq_agent, "LOT_PICKUP_LINE", True)


def test_off_by_default_keeps_lot_1s_truck():
    assert rfq_agent.LOT_PICKUP_LINE is False
    api = LineApi()
    lots, _ = rfq_agent._multi_quote(1, MAIL, R185, YYZ_QUOTE, [JUNIPER, DOMBLICK], api)
    assert lots[1]["option"]["total"] == 2593.37 and api.asked == [([DOMBLICK], False)]


def test_r185_lot_2_gets_a_pickup_for_its_own_weight(on):
    api = LineApi()
    lots, text = rfq_agent._multi_quote(1, MAIL, R185, YYZ_QUOTE, [JUNIPER, DOMBLICK], api)
    assert api.asked == [([], True)]  # no lot 1 truck bid sent, the backend estimates the 620 kg pickup
    assert lots[1]["option"]["total"] == 2428.0 and "2,428.00" in text and "2,593.37" not in text


def test_no_estimate_falls_back_to_lot_1s_truck(on):
    api = LineApi(estimate=None)
    lots, _ = rfq_agent._multi_quote(1, MAIL, R185, YYZ_QUOTE, [JUNIPER, DOMBLICK], api)
    assert lots[1]["option"]["total"] == 2593.37 and api.asked[-1] == ([DOMBLICK], False)


def test_lot_2s_own_trucker_bid_wins(on):
    own = {**DOMBLICK, "rate_id": "TRK-2", "total": 221.10}
    api = LineApi()
    lots, _ = rfq_agent._multi_quote(1, MAIL, R185, YYZ_QUOTE, [JUNIPER, DOMBLICK], api,
                                     {1: {"destination": "BOM", "bids": [own]}})
    assert api.asked == [([own], False)] and lots[1]["option"]["total"] == 2434.5


def test_a_shared_truck_share_wins(on):
    truck = {**DOMBLICK, "total": 439.70, "truck_total": 439.70, "truck_kg": 2351.4}
    api = LineApi()
    rfq_agent._multi_quote(1, MAIL, R185, YYZ_QUOTE, [JUNIPER, truck], api)
    (used, fallback), = api.asked
    assert fallback is False and used[0]["truck_share"] < 0.3
