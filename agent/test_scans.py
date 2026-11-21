"""Scanned attachments (scans.py): read into text so DG, totals and constraints see them. No live call: llm is mocked."""
import base64
import io
import struct
import zipfile

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

    def fake(name, system, user, schema, model=None, timeout=None, max_tokens=None):
        seen.update(name=name, user=user, model=model, timeout=timeout, max_tokens=max_tokens)
        return {"text": "  UN1133, Class 3  "}, 0.0012

    monkeypatch.setattr(llm, "chat_json", fake)
    assert scans.read("Packing_List.JPG", PNG) == ("UN1133, Class 3", 0.0012)
    part = seen["user"][0]
    assert part["type"] == "image_url" and part["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert seen["model"] == scans.MODEL and seen["model"] in llm.PRICES and seen["timeout"] == scans.TIMEOUT_S
    assert seen["max_tokens"] == scans.MAX_TOKENS


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
    with pytest.raises(ValueError):  # a long scanned PDF: cost and time
        scans.read("manual.pdf", b"%PDF " + b"<< /Type /Page >> " * (scans.MAX_PDF_PAGES + 1) + b"<< /Type /Pages >>")
    assert scans.pdf_pages(b"<< /Type /Pages >> << /Type /Page >> << /Type/Page >>") == 2
    assert scans.readable("scan.jpeg") and scans.readable("x.PDF") and not scans.readable("list.xlsx")


def _rfq(tmp_path, monkeypatch, filename, backend_text="", scan=None, data=PNG):
    """Runs one RFQ with one attachment; `scan` replaces scans.read (a function, or an exception to raise)."""
    calls = []
    monkeypatch.setattr(scans, "_done", {})

    def fake_read(name, data, timeout=None):
        calls.append(name)
        if isinstance(scan, Exception):
            raise scan
        return scan, 0.0012

    monkeypatch.setattr(scans, "read", fake_read)
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**RAW, "pickup_address": None}, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    api.attachment_text = lambda name, content: backend_text
    att = [{"filename": filename, "content_base64": base64.b64encode(data).decode()}]
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


def test_a_scan_is_paid_for_once_even_when_the_rfq_resumes(tmp_path, monkeypatch):
    """The pickup-answer path reads the attachments again: the second read is free, failed or not."""
    monkeypatch.setattr(scans, "_done", {})
    calls = []

    def fake(name, data, timeout=None):
        calls.append(timeout)
        return SCAN, 0.0012

    monkeypatch.setattr(scans, "read", fake)
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    api.attachment_text = lambda name, content: ""
    mail = {**MAIL, "attachments": [{"filename": "pl.jpg", "content_base64": base64.b64encode(PNG).decode()}]}
    first, second = [], []
    assert rfq_agent._attachment_texts(1, mail, box, api, first) == [SCAN]
    assert rfq_agent._attachment_texts(1, mail, box, api, second) == [SCAN]
    assert len(calls) == 1 and first == [0.0012] and second == [0.0]
    assert 0 < calls[0] <= scans.TIMEOUT_S

    monkeypatch.setattr(scans, "read", lambda *a: (_ for _ in ()).throw(TimeoutError("slow")))
    other = {**mail, "id": "m2"}
    assert rfq_agent._attachment_texts(1, other, box, api) == [""]
    monkeypatch.setattr(scans, "read", lambda *a: pytest.fail("a failed scan is not read again"))
    assert rfq_agent._attachment_texts(1, other, box, api) == [""]


def test_no_scan_once_the_time_budget_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(scans, "BUDGET_S", 0.0)
    box, api, calls = _rfq(tmp_path, monkeypatch, "scan.jpg", scan="unused")
    assert calls == [] and "quote_sent" in api.events


# --- picture parts next to typed text: a scanned page in a PDF, a picture pasted into Word/Excel/PowerPoint ---

def _png(width, height):
    """Only the header: the size check reads it, the bytes never reach a model here."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", width, height) + b"\x08\x02" + b"\x00" * 40


def _jpeg(width, height, fill=b"\x00" * 40):
    sof = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, height, width) + b"\x03" + b"\x00" * 9
    return b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + sof + fill + b"\xff\xd9"


def _office(pictures: dict, text_part=("word/document.xml", "<w:t>Packing list: 4 cartons, 120 kg</w:t>")) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(*text_part)
        for name, data in pictures.items():
            z.writestr(name, data)
    return out.getvalue()


def _pdf(images: list[tuple[int, int, bytes | None]], pages: int = 1) -> bytes:
    """A PDF with a text page and image XObjects (raw gray, or a JPEG when given)."""
    out = b"%PDF-1.4\n1 0 obj <</Type/Catalog/Pages 2 0 R>> endobj\n" + b"2 0 obj <</Type/Pages/Count %d>> endobj\n" % pages
    out += b"".join(b"%d 0 obj <</Type/Page/Parent 2 0 R>> endobj\n" % (10 + i) for i in range(pages))
    out += b"3 0 obj <</Length 44>>stream\nBT /F1 12 Tf (Shippers Letter: 120 kg) Tj ET\nendstream endobj\n"
    for number, (width, height, jpeg) in enumerate(images, 20):
        body = jpeg or b"\xff" * 64
        kind = b"/Filter/DCTDecode" if jpeg else b""
        out += (b"%d 0 obj\n<</Type/XObject/Subtype/Image/Width %d/Height %d/ColorSpace/DeviceGray/BitsPerComponent 8"
                % (number, width, height) + kind + b"/Length %d>>stream\n" % len(body) + body + b"\nendstream\nendobj\n")
    return out + b"%%EOF"


TEXT = "Packing list: 4 cartons, 120 kg"


def test_which_attachments_have_a_picture_part_to_read():
    page, logo = _png(1240, 1754), _png(64, 64)
    assert scans.needs_scan("PL.docx", _office({"word/media/image1.png": page}), TEXT)
    assert scans.needs_scan("PL.xlsx", _office({"xl/media/image1.jpeg": _jpeg(1000, 700)}), TEXT)
    assert scans.needs_scan("PL.pptx", _office({"ppt/media/image3.png": page}), TEXT)
    assert scans.needs_scan("PL.odt", _office({"Pictures/1.png": page}), TEXT)
    assert not scans.needs_scan("PL.docx", _office({"word/media/image1.png": logo}), TEXT)  # an icon costs nothing
    assert not scans.needs_scan("PL.docx", _office({}), TEXT)
    assert not scans.needs_scan("PL.docx", b"not a zip", TEXT)
    assert scans.needs_scan("SLI.pdf", _pdf([(1654, 2339, None)], pages=2), TEXT)  # typed page 1, scanned page 2
    assert not scans.needs_scan("SLI.pdf", _pdf([(64, 64, None)]), TEXT)  # typed PDF with an icon
    assert not scans.needs_scan("SLI.pdf", _pdf([]), TEXT)
    assert scans.needs_scan("SLI.pdf", _pdf([]), "")  # no text at all: the whole PDF, as before
    assert scans.needs_scan("PL.jpg", page, "") and not scans.needs_scan("PL.jpg", page, TEXT)
    assert not scans.needs_scan("PL.csv", b"a,b", "") and not scans.needs_scan("memo.mp3", b"x", "")


def test_pictures_inside_an_office_file_go_in_one_call_largest_first_logos_left_out(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (seen.update(user=a[2]) or {"text": "UN3480"}, 0.002))
    pictures = {"word/media/icon.png": _png(64, 64), "word/media/a.png": _png(800, 600),
                "word/media/b.jpeg": _jpeg(1240, 1754), "word/media/c.png": _png(900, 700),
                "word/media/d.png": _png(700, 500), "word/media/e.emf": b"x" * 50_000}
    assert scans.read("PL.docx", _office(pictures)) == ("UN3480", 0.002)
    urls = [p["image_url"]["url"] for p in seen["user"]]
    assert len(urls) == scans.MAX_PICTURES and urls[0].startswith("data:image/jpeg;base64,")
    assert all(u.startswith(("data:image/png;base64,", "data:image/jpeg;base64,")) for u in urls)
    assert base64.b64encode(_png(64, 64)).decode() not in "".join(urls)


def test_a_long_scanned_pdf_reads_the_jpegs_of_its_first_three_pages(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (seen.update(user=a[2]) or {"text": "p1 p2 p3"}, 0.002))
    jpegs = [_jpeg(1654, 2339, bytes([i]) * 40) for i in range(5)]
    assert scans.read("scan.pdf", _pdf([(1654, 2339, j) for j in jpegs], pages=5))[0] == "p1 p2 p3"
    urls = [p["image_url"]["url"] for p in seen["user"]]
    assert urls == [f"data:image/jpeg;base64,{base64.b64encode(j).decode()}" for j in jpegs[:3]]
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: pytest.fail("no call"))
    with pytest.raises(ValueError):  # long, and its pages aren't JPEGs: not read (as before)
        scans.read("scan.pdf", _pdf([(1654, 2339, None)] * 5, pages=5))
    with pytest.raises(ValueError):
        scans.read("PL.docx", _office({"word/media/icon.png": _png(64, 64)}))


def test_a_typed_pdf_with_a_scanned_page_is_sent_whole_up_to_three_pages(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (seen.update(user=a[2]) or {"text": "UN3480"}, 0.001))
    scans.read("SLI.pdf", _pdf([(1654, 2339, None)], pages=2))
    assert [p["type"] for p in seen["user"]] == ["file"]


def test_dg_on_a_picture_in_a_typed_word_file_is_found_and_the_typed_text_kept(tmp_path, monkeypatch):
    docx = _office({"word/media/image1.png": _png(1240, 1754)})
    box, api, calls = _rfq(tmp_path, monkeypatch, "Packing_List.docx", backend_text=TEXT, scan=SCAN, data=docx)
    assert calls == ["Packing_List.docx"]
    rfq = api.data["extracted"]
    assert rfq["dangerous_goods"] is True and "UN1133" in rfq["dg_declared"]
    assert any(u.get("llm_cost_usd") == pytest.approx(0.0013) for u in api.updates)  # extraction + scan
    assert "quote_sent" in api.events


def test_typed_text_and_the_scan_are_joined_and_a_failed_read_keeps_the_typed_text(tmp_path, monkeypatch):
    monkeypatch.setattr(scans, "_done", {})
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    api.attachment_text = lambda name, content: TEXT
    pdf = _pdf([(1654, 2339, None)], pages=2)
    mail = {**MAIL, "attachments": [{"filename": "SLI.pdf", "content_base64": base64.b64encode(pdf).decode()}]}
    monkeypatch.setattr(scans, "read", lambda name, data, timeout=None: (SCAN, 0.001))
    costs = []
    assert rfq_agent._attachment_texts(1, mail, box, api, costs) == [f"{TEXT}\n{SCAN}"] and costs == [0.001]
    monkeypatch.setattr(scans, "read", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("slow")))
    assert rfq_agent._attachment_texts(1, {**mail, "id": "m9"}, box, api) == [TEXT]


def test_a_typed_file_without_pictures_costs_nothing(tmp_path, monkeypatch):
    _, api, calls = _rfq(tmp_path, monkeypatch, "PL.docx", backend_text=TEXT, scan="unused",
                         data=_office({"word/media/icon.png": _png(64, 64)}))
    assert calls == [] and "quote_sent" in api.events


def _png(width: int, height: int) -> bytes:
    """A PNG header with these dimensions (scans._dims only reads the IHDR)."""
    import struct
    import zlib
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))


def _docx_with(*pictures: bytes) -> bytes:
    import io
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:t>Packing list: 3 pallets, 640 kg</w:t></w:document>")
        for i, picture in enumerate(pictures):
            z.writestr(f"word/media/image{i}.png", picture)
    return buffer.getvalue()


@pytest.mark.parametrize("sizes", [[(300, 100)], [(120, 90)], [(200, 60)], [(600, 180), (250, 80)], [(400, 120)]])
def test_logos_and_signatures_in_a_typed_file_never_cost_a_call(sizes):
    """Review of #175: letterheads and signatures sit in most business documents."""
    assert not scans.needs_scan("packing.docx", _docx_with(*[_png(w, h) for w, h in sizes]), "Packing list")


@pytest.mark.parametrize("size", [(900, 400), (1240, 1754)])
def test_a_pasted_screenshot_or_scanned_page_still_triggers(size):
    assert scans.needs_scan("packing.docx", _docx_with(_png(*size), _png(300, 100)), "Packing list")
    assert [name for name, _ in scans.office_pictures(_docx_with(_png(*size), _png(300, 100)))] == ["word/media/image0.png"]
