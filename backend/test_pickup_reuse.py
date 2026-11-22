"""PICKUP_LINE: earlier trucker bids for the fallback quote, priced for this weight (pickup_reuse.py)."""
import pickup_reuse
from crm import Crm
from fastapi.testclient import TestClient

from app import create_app
from test_app import FakeMailbox


def _bid(carrier, total):
    return {"source": "carrier_bid", "leg": "pickup", "carrier": carrier, "currency": "EUR", "total": total,
            "transit_days": 0.8, "rate_id": "T-1"}


def test_the_truckers_line_prices_another_weight_exactly():
    # live zone 24 bids of Maintal Transport Logistik: 77 + 0.07/kg
    seen = {"Maintal": [(1082, _bid("Maintal", 152.74)), (859, _bid("Maintal", 137.13))]}
    [bid] = pickup_reuse.estimate(seen, 1619, 0.5)
    assert bid["total"] == 190.33 and bid["rate_id"] is None and "2 earlier bids" in bid["estimated_from"]


def test_one_bid_is_reused_only_near_its_weight():
    seen = {"Flink": [(859, _bid("Flink", 182.08))]}
    assert pickup_reuse.estimate(seen, 1000, 0.5)[0]["total"] == 182.08
    assert pickup_reuse.estimate(seen, 2000, 0.5) == []


def test_points_off_one_line_fall_back_to_the_nearby_bid():
    # zone 22: the base depends on the address, the three bids are not on one line
    seen = {"Kranich": [(1139, _bid("Kranich", 339.56)), (1034, _bid("Kranich", 282.40)), (658, _bid("Kranich", 222.28))]}
    assert pickup_reuse.estimate(seen, 1100, 0.5)[0]["total"] == 339.56  # the newest within ±50 %


def test_switch_off_keeps_the_nearby_bid_only(monkeypatch):
    monkeypatch.setattr(pickup_reuse, "ON", False)
    seen = {"Maintal": [(1082, _bid("Maintal", 152.74)), (859, _bid("Maintal", 137.13))]}
    assert pickup_reuse.estimate(seen, 1619, 0.5)[0]["total"] == 152.74


def test_the_fallback_price_uses_earlier_sessions_of_the_zone():
    crm = Crm(":memory:")
    for kg, total in ((859, 137.13), (1082, 152.74)):
        sid = crm.create_session("a@b.c", f"t{kg}")
        crm.update(sid, {"rfq": {"origin": "HAM", "destination": "JFK", "pickup": {"address": "24489 Kiel"},
                                 "pieces": [{"count": 1, "weight_kg": kg}], "volume_m3": 1},
                         "bids": [_bid("Maintal Transport Logistik", total)]})
    client = TestClient(create_app(crm, FakeMailbox()))
    rfq = {"origin": "HAM", "destination": "JFK", "pickup": {"address": "24983 Kiel"}, "ready_date": "2026-11-25",
           "pieces": [{"count": 1, "weight_kg": 1619, "length_cm": None, "width_cm": None, "height_cm": None}],
           "volume_m3": 1}
    result = client.post("/api/price", json={"rfq": rfq, "bids": [], "fallback": True}).json()
    assert "190.33" in result["why"] or any((o.get("pickup") or {}).get("total") == 190.33 for o in result["options"])
