import httpx
from fastapi.testclient import TestClient

from app import create_app
from crm import Crm
from portal import Portal
from pricing import Pricer
from tariffs import Tariffs, Zones

RFQ = {"origin": "FRA", "destination": "LAX", "ask": "cheapest", "pickup": None, "ready_date": "2026-11-23",
       "pieces": [{"count": 1, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 90}],
       "volume_m3": 0.1}


def booking_out(rate_id, reference, status=201):
    return httpx.Response(status, json={
        "booking_reference": "BK-1A2B3C4D", "team_reference": reference, "rate_id": rate_id,
        "airline": "Gannet Airways", "airline_code": "GN", "price": "350.00", "currency": "EUR", "status": "booked"})


def setup(portal_answers: dict):
    """portal_answers: rate_id → HTTP status for bookings. GET rates always returns R-fresh0001."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/portal/bookings":
            body = __import__("json").loads(request.content)
            seen.append(("book", body["rate_id"], body["team_reference"]))
            status = portal_answers.get(body["rate_id"], 404)
            if status in (200, 201):
                return booking_out(body["rate_id"], body["team_reference"], status)
            return httpx.Response(status, json={"detail": f"status {status}"})
        if request.url.path == "/v1/portal/rates":
            q = request.url.params
            seen.append(("rate", q["airline"], float(q["weight_kg"]), float(q["volume_cbm"])))
            return httpx.Response(200, json={"rate_id": "R-fresh0001", "airline": "Gannet Airways",
                                             "airline_code": "GN", "chargeable_weight_kg": "100", "total": "355.00",
                                             "currency": "EUR", "transit_days": 3,
                                             "valid_until": "2099-01-01T00:00:00+00:00"})
        return httpx.Response(404)

    portal = Portal(base_url="https://portal.test", api_key="k", transport=httpx.MockTransport(handler))
    app = create_app(Crm(":memory:"), None, Pricer(Tariffs(), Zones(), portal))
    c = TestClient(app)
    sid = c.post("/api/sessions", json={"customer": "a@x.example", "thread_id": 1}).json()["id"]
    return c, sid, seen


def quote(rate_id, **extra):
    return {"source": "portal", "carrier": "Gannet Airways", "airline_code": "GN", "rate_id": rate_id,
            "currency": "EUR", "total": 350.0, "transit_days": 3, "chargeable_weight_kg": 90, "billed_weight_kg": 90,
            **extra}


def test_books_the_quoted_rate():
    c, sid, seen = setup({"R-quoted0001": 201})
    c.patch(f"/api/sessions/{sid}", json={"rfq": RFQ, "quote": quote("R-quoted0001")})
    booking = c.post("/api/book", json={"session_id": sid, "rate_id": "R-quoted0001"}).json()
    assert booking["booking_reference"] == "BK-1A2B3C4D" and booking["team_reference"] == f"S-{sid}"
    assert ("book", "R-quoted0001", f"S-{sid}") in seen


def test_rate_id_defaults_to_the_quote():
    c, sid, seen = setup({"R-quoted0001": 201})
    c.patch(f"/api/sessions/{sid}", json={"rfq": RFQ, "quote": quote("R-quoted0001")})
    assert c.post("/api/book", json={"session_id": sid, "rate_id": None}).status_code == 200


def test_expired_rate_is_repriced_at_the_billed_break_and_booked():
    c, sid, seen = setup({"R-quoted0001": 410, "R-fresh0001": 201})
    c.patch(f"/api/sessions/{sid}", json={"rfq": RFQ, "quote": quote("R-quoted0001", billed_weight_kg=100)})
    booking = c.post("/api/book", json={"session_id": sid, "rate_id": "R-quoted0001"}).json()
    assert booking["rate_id"] == "R-fresh0001"
    assert ("rate", "GN", 100.0, 0.0) in seen  # same break as quoted
    events = c.get(f"/api/sessions/{sid}/events").json()
    assert events[-1]["kind"] == "priced" and "expired" in events[-1]["text"]


def test_sheet_option_and_portal_refusal_are_502():
    c, sid, _ = setup({"R-taken00001": 409})
    c.patch(f"/api/sessions/{sid}", json={"rfq": RFQ, "quote": {**quote(None), "source": "sheet"}})
    response = c.post("/api/book", json={"session_id": sid, "rate_id": None})
    assert response.status_code == 502 and "by email" in response.json()["detail"]
    response = c.post("/api/book", json={"session_id": sid, "rate_id": "R-taken00001"})
    assert response.status_code == 502 and "409" in response.json()["detail"]
    assert c.post("/api/book", json={"session_id": 999, "rate_id": "R-x"}).status_code == 404
