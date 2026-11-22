"""POST /api/cancel: a portal booking cancelled with DELETE /v1/portal/bookings/{ref}; cancelled only on a 2xx."""
import httpx
from fastapi.testclient import TestClient

from app import create_app
from crm import Crm
from portal import Portal
from pricing import Pricer
from tariffs import Tariffs, Zones
from test_app import FakeMailbox


def _client(status):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(status, json={"status": "cancelled"} if status < 300 else {"detail": "unknown booking"})

    crm = Crm(":memory:")
    portal = Portal(base_url="https://portal.test", api_key="k", transport=httpx.MockTransport(handler))
    return TestClient(create_app(crm, FakeMailbox(), Pricer(Tariffs(), Zones(), portal))), crm, calls


def _booked(crm, **booking):
    sid = crm.create_session("anna@customer.test", "t1")
    crm.update(sid, {"booking": {"booking_reference": "BK-1", "status": "confirmed", "airline": "Gannet Airways",
                                 **booking}})
    return sid


def test_a_2xx_cancels_the_portal_booking_once():
    client, crm, calls = _client(200)
    sid = _booked(crm)
    out = client.post("/api/cancel", json={"session_id": sid}).json()
    assert out["status"] == "cancelled" and calls == [("DELETE", "/v1/portal/bookings/BK-1")]
    assert crm.session(sid)["booking"]["status"] == "cancelled"
    assert client.post("/api/cancel", json={"session_id": sid}).json()["status"] == "cancelled" and len(calls) == 1


def test_any_other_answer_is_not_cancelled():
    client, crm, calls = _client(404)
    sid = _booked(crm)
    response = client.post("/api/cancel", json={"session_id": sid})
    assert response.status_code == 502 and crm.session(sid)["booking"]["status"] == "confirmed"


def test_an_email_booking_is_never_cancelled_on_the_portal():
    client, crm, calls = _client(200)
    sid = _booked(crm, pending_email="gannet-airways@hackloop.mail")
    assert client.post("/api/cancel", json={"session_id": sid}).status_code == 409 and calls == []


def test_a_cancel_counts_against_the_minutes_portal_budget():
    import asyncio
    portal = Portal(base_url="https://portal.test", api_key="k",
                    transport=httpx.MockTransport(lambda request: httpx.Response(204)))
    asyncio.run(portal.cancel("BK-1"))
    assert portal.calls_left() == 9
