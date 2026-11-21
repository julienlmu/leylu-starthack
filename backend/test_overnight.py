"""Overnight safety (docs/ORHUN_FIXES.md P1): nothing a mail or a restart can do should stop pricing or double-book."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app import create_app
from crm import Crm
from ingest import TariffError, _date, parse_tariff
from portal import Portal
from pricing import Pricer
from tariffs import DATA, Tariffs, Zones
from test_booking import RFQ, quote, setup
from test_app import FakeMailbox

KIT = DATA / "start-kit"


def test_a_truncated_ingested_tariff_does_not_stop_the_backend(tmp_path):
    (tmp_path / "broken-2026-12-01.json").write_text('{"sheets": [{"airline": "Kes')
    app = create_app(Crm(":memory:"), FakeMailbox(), None, ingest_dir=tmp_path)
    assert TestClient(app).get("/health").json() == {"ok": True}
    assert len(app.state.pricer.tariffs.sheets) == 10  # the start-kit sheets are all there


def test_dates_are_real_dates():
    assert _date("01/11/2026") == "2026-11-01"      # day/month, as in the kit
    assert _date("11/30/2026") == "2026-11-30"      # only valid as month/day
    assert _date("2026-30-11") is None              # no month 30
    assert _date("31 November 2026") is None


def test_backwards_validity_is_refused():
    text = (KIT / "yellowtail-air-freight-tariff-2026-11.txt").read_text().replace("Valid to    30.11.2026", "Valid to    01.10.2026")
    with pytest.raises(TariffError, match="backwards"):
        parse_tariff("yellowtail.txt", text.encode())


def test_a_manual_reply_pauses_the_agent_first():
    box = FakeMailbox()
    c = TestClient(create_app(Crm(":memory:"), box))
    sid = c.post("/api/sessions", json={"customer": "a@x.example", "thread_id": 5}).json()["id"]
    assert c.post(f"/api/sessions/{sid}/intervene", json={"action": "send", "body": "Our offer …"}).json()["paused"] is True
    assert len(box.sent) == 1


def test_a_lost_portal_answer_never_books_a_second_fresh_rate():
    calls = {"n": 0}
    c, sid, seen = setup({"R-quoted0001": 410, "R-fresh0001": 201})
    c.patch(f"/api/sessions/{sid}", json={"rfq": RFQ, "quote": quote("R-quoted0001", total=360.0)})
    portal = c.app.state.pricer.portal
    real_book = portal.book

    async def flaky_book(rate_id, reference):
        calls["n"] += 1
        if rate_id == "R-fresh0001" and calls["n"] == 2:  # the portal books it, but the answer never arrives
            await real_book(rate_id, reference)
            raise httpx.ReadTimeout("lost")
        return await real_book(rate_id, reference)

    portal.book = flaky_book
    assert c.post("/api/book", json={"session_id": sid, "rate_id": None}).status_code == 502
    assert c.get(f"/api/sessions/{sid}").json()["booking"]["pending_rate_id"] == "R-fresh0001"
    second = c.post("/api/book", json={"session_id": sid, "rate_id": None}).json()
    assert second["rate_id"] == "R-fresh0001"
    assert not any(s[0] == "rate" for s in seen[seen.index(("book", "R-fresh0001", f"S-{sid}")) + 1:])  # no new fresh rate


def test_fallback_pricing_uses_earlier_trucker_bids_for_the_zone():
    from test_pricing import TARIFFS
    c = TestClient(create_app(Crm(":memory:"), FakeMailbox(), Pricer(TARIFFS, Zones(), Portal(api_key=""))))
    pickup = {"address": "Mainzer Landstr. 5, 60311 Frankfurt", "zone": None}
    rfq = {"origin": "FRA", "destination": "LAX", "ask": "cheapest", "pickup": pickup, "ready_date": "2026-11-23",
           "pieces": [{"count": 1, "weight_kg": 300}], "volume_m3": 2.5}
    old = c.post("/api/sessions", json={"customer": "a@x.example", "thread_id": 1}).json()["id"]
    c.patch(f"/api/sessions/{old}", json={"rfq": rfq, "bids": [
        {"source": "carrier_bid", "leg": "pickup", "carrier": "Taunusfracht", "currency": "EUR", "total": 90.0,
         "transit_days": 1, "rate_id": "TRK-1"}]})
    assert c.post("/api/price", json={"rfq": rfq, "bids": []}).json()["chosen"] is None  # no trucker answered
    fallback = c.post("/api/price", json={"rfq": rfq, "bids": [], "fallback": True}).json()
    assert fallback["chosen"]["pickup"]["carrier"] == "Taunusfracht" and fallback["chosen"]["total"] == 1250.66
