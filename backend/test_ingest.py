import base64
import json

import pytest
from fastapi.testclient import TestClient

from app import create_app
from crm import Crm
from ingest import TariffError, parse_tariff
from portal import Portal
from pricing import Pricer
from tariffs import DATA, Tariffs, Zones

KIT = DATA / "start-kit"
TRUTH = {s["file"]: s for s in json.loads((DATA / "tariffs.json").read_text())["sheets"]}
SHEETS = sorted(p.name for p in KIT.iterdir() if "tariff" in p.name and not p.name.endswith(".jpg"))


@pytest.mark.parametrize("name", SHEETS)
def test_every_start_kit_layout_parses_exactly(name):
    """9 layouts (txt, 3 PDFs, docx, 4 xlsx) give the same numbers as the hand-checked normalized file."""
    got, truth = parse_tariff(name, (KIT / name).read_bytes()), TRUTH[name]
    for key in ("airline", "currency", "breaks_kg", "valid_from", "valid_to", "cbm_kg"):
        assert got[key] == truth[key], key
    assert {l["lane"]: l for l in got["lanes"]} == {l["lane"]: l for l in truth["lanes"]}


def test_images_and_junk_are_refused():
    with pytest.raises(TariffError, match="image"):
        parse_tariff("danube-wings-cargo-tariff-2026-12-p1.jpg", (KIT / "danube-wings-cargo-tariff-2026-11-p1.jpg").read_bytes())
    with pytest.raises(TariffError):
        parse_tariff("notes.txt", b"Hello, see you tomorrow")


def december(name: str) -> bytes:
    """A December tariff in the same layout: Yellowtail's November sheet with new dates and rates × 2."""
    text = (KIT / name).read_text().replace("01.11.2026", "01.12.2026").replace("30.11.2026", "31.12.2026")
    return text.replace("EUR 5.92", "EUR 11.84").encode()


def test_ingest_endpoint_adds_saves_and_prices_with_the_new_tariff(tmp_path):
    pricer = Pricer(Tariffs.from_files(DATA / "tariffs.json"), Zones(), Portal(api_key=""))
    c = TestClient(create_app(Crm(":memory:"), None, pricer, ingest_dir=tmp_path))
    body = {"filename": "yellowtail-air-freight-tariff-2026-12.txt", "from": "yellowtail-air-freight@hackloop.mail",
            "content_base64": base64.b64encode(december("yellowtail-air-freight-tariff-2026-11.txt")).decode()}
    assert c.post("/api/tariffs/ingest", json=body).json() == {"rows": 15, "airline": "Yellowtail Air Freight",
                                                               "valid_until": "2026-12-31"}
    assert (tmp_path / "yellowtail-air-freight-2026-12-01.json").exists()

    rfq = {"origin": "CGN", "destination": "SYD", "ask": "cheapest", "pickup": None,
           "pieces": [{"count": 1, "weight_kg": 30}], "volume_m3": 0}
    nov = c.post("/api/price", json={"rfq": {**rfq, "ready_date": "2026-11-25"}, "bids": []}).json()
    dec = c.post("/api/price", json={"rfq": {**rfq, "ready_date": "2026-12-02"}, "bids": []}).json()
    yellow = lambda r: next(o for o in r["options"] if o["carrier"] == "Yellowtail Air Freight")  # noqa: E731
    assert yellow(nov)["breakdown"][0]["label"] == "Freight 30 kg × 5.92"
    # December: the first bracket now costs 11.84/kg, so billing at the 45 kg break (5.03/kg) is cheaper
    assert yellow(dec)["breakdown"][0]["label"] == "Freight 45 kg × 5.03"
    assert [o["carrier"] for o in dec["options"]] == ["Yellowtail Air Freight"]  # the November sheets ended

    # a restart loads the saved tariff again
    reloaded = create_app(Crm(":memory:"), None, None, ingest_dir=tmp_path)
    assert any(s["valid_from"] == "2026-12-01" for s in reloaded.state.pricer.tariffs.sheets)


def test_ingest_endpoint_reports_what_it_cannot_read(tmp_path):
    c = TestClient(create_app(Crm(":memory:"), None, None, ingest_dir=tmp_path))
    body = {"filename": "danube.jpg", "from": "danube-wings-cargo@hackloop.mail",
            "content_base64": base64.b64encode(b"\xff\xd8\xff").decode()}
    result = c.post("/api/tariffs/ingest", json=body).json()
    assert result["rows"] == 0 and "image" in result["error"]
    assert not list(tmp_path.iterdir())
