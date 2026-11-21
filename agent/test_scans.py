"""Scanned attachments (scans.py): read into text so DG, totals and constraints see them. No live call: llm is mocked."""
import base64

import pytest

import extract as extract_mod
import llm
import rfq_agent
import scans
from bids import BidBoard
from inbox import FixtureMailbox
from test_rfq_agent import CARRIERS, MAIL, OPTION, RAW, FakeApi

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # the bytes never reach a model here
SCAN = "PACKING LIST\nPcs | Goods | Gross kg\n4 | Adhesives | 855\nDangerous goods: UN1133, Class 3, Adhesives"


def test_an_image_is_sent_as_an_image_part_with_a_short_timeout(monkeypatch):
    seen = {}

    def fake(name, system, user, schema, model=None, timeout=None):
        seen.update(name=name, user=user, model=model, timeout=timeout)
        return {"text": "  UN1133, Class 3  "}, 0.0012

    monkeypatch.setattr(llm, "chat_json", fake)
    assert scans.read("Packing_List.JPG", PNG) == ("UN1133, Class 3", 0.0012)
    part = seen["user"][0]
    assert part["type"] == "image_url" and part["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert seen["model"] == scans.MODEL and seen["model"] in llm.PRICES and seen["timeout"] == scans.TIMEOUT_S


def test_a_pdf_without_text_is_sent_as_a_file(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (seen.update(user=a[2]) or {"text": "SLI"}, 0.001))
    assert scans.read("SLI_4711.pdf", b"%PDF-1.4 scanned")[0] == "SLI"
    assert seen["user"][0]["type"] == "file" and seen["user"][0]["file"]["file_data"].startswith(
        "data:application/pdf;base64,")


def test_what_is_never_read(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: pytest.fail("no call"))
    with pytest.raises(ValueError):
        scans.read("packing.xls", b"x")
    with pytest.raises(ValueError):
        scans.read("huge.png", b"x" * (scans.MAX_BYTES + 1))
    assert scans.readable("scan.jpeg") and scans.readable("x.PDF") and not scans.readable("list.xlsx")


def _rfq(tmp_path, monkeypatch, filename, backend_text="", scan=None):
    """Runs one RFQ with one attachment; `scan` replaces scans.read (a function, or an exception to raise)."""
    calls = []

    def fake_read(name, data):
        calls.append(name)
        if isinstance(scan, Exception):
            raise scan
        return scan, 0.0012

    monkeypatch.setattr(scans, "read", fake_read)
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**RAW, "pickup_address": None}, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    api.attachment_text = lambda name, content: backend_text
    att = [{"filename": filename, "content_base64": base64.b64encode(PNG).decode()}]
    rfq_agent.handle_rfq({**MAIL, "attachments": att}, box, api, BidBoard(), CARRIERS, cutoff_s=0.1)
    return box, api, calls


def test_dg_in_a_scanned_packing_list_is_found_and_its_cost_counted(tmp_path, monkeypatch):
    box, api, calls = _rfq(tmp_path, monkeypatch, "PL_53839.jpg", scan=SCAN)
    assert calls == ["PL_53839.jpg"]
    rfq = api.data["extracted"]
    assert rfq["dangerous_goods"] is True and "UN1133" in rfq["dg_declared"]
    assert any(u.get("llm_cost_usd") == pytest.approx(0.0013) for u in api.updates)  # extraction + scan
    assert "quote_sent" in api.events and box.sent[-1]["thread_id"] == "t1"


@pytest.mark.parametrize("failure", [TimeoutError("gateway slow"), RuntimeError("model refused")])
def test_a_failed_read_never_stops_the_quote(tmp_path, monkeypatch, failure):
    box, api, calls = _rfq(tmp_path, monkeypatch, "scan.png", scan=failure)
    assert calls == ["scan.png"] and "quote_sent" in api.events and "error" not in api.events


def test_an_empty_read_is_reported_and_still_quoted(tmp_path, monkeypatch):
    box, api, _ = _rfq(tmp_path, monkeypatch, "blank.png", scan="")
    assert "quote_sent" in api.events and "error" not in api.events


def test_no_call_for_a_pdf_with_text_or_when_switched_off(tmp_path, monkeypatch):
    _, api, calls = _rfq(tmp_path, monkeypatch, "spec.pdf", backend_text="Gross weight 440 lb", scan="unused")
    assert calls == [] and "quote_sent" in api.events
    monkeypatch.setattr(scans, "IMAGE_READ", False)
    _, api, calls = _rfq(tmp_path / "off", monkeypatch, "scan.jpg", scan="unused")
    assert calls == [] and "quote_sent" in api.events
