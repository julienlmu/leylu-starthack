"""Attachment traps through the whole RFQ path (sweep of Sun 00:15): a long PDF whose later pages are scans we can't
decode, archives we can't open (AES zip, RAR, 7z), a tariff that arrives as a photo. Files built here; the image
reader is mocked, nothing leaves the machine."""

import base64
import io
import sys
import zipfile
from pathlib import Path

import pytest

import main
import scans
from test_traps import CASES, run

OPTIONS = CASES[2]["options"]
BODY = "Hello, 3 pallets machine parts FRA to GRU, 715 kg, 2.65 cbm, ready 25.11. Documents attached."


def _att(name: str, data: bytes) -> dict:
    return {"id": name, "filename": name, "content_base64": base64.b64encode(data).decode()}


def _case(name: str, data: bytes, body: str = BODY) -> dict:
    return {"name": name, "body": body, "options": OPTIONS, "chosen": 0, "attachments": [_att(name, data)]}


def _aes_zip(files: dict, open_files=()) -> bytes:
    """A zip whose members (except `open_files`) are marked WinZip-AES encrypted (method 99): zipfile can't decrypt it."""
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    data = bytearray(raw.getvalue())
    # local header: flags at +6, method at +8, name at +30; central directory: +8, +10, +46
    for sig, flags_at, name_at in ((b"PK\x03\x04", 6, 30), (b"PK\x01\x02", 8, 46)):
        at = data.find(sig)
        while at >= 0:
            name = data[at + name_at:].split(b"PK", 1)[0]
            if not any(name.startswith(n.encode()) for n in open_files):
                data[at + flags_at:at + flags_at + 4] = (1).to_bytes(2, "little") + (99).to_bytes(2, "little")
            at = data.find(sig, at + 4)
    return bytes(data)


# ---- 9: a long PDF, typed page 1, then scans stored as CCITT / JBIG2 / Flate (no JPEG to cut out) ------------------
FILTERS = [b"/CCITTFaxDecode", b"/JBIG2Decode", b"/FlateDecode"]


def _long_pdf(scanned: int) -> bytes:
    """Page 1: typed packing list without DG. Then `scanned` pages, each one 1240 x 1754 picture in another codec."""
    text = b"BT /F1 11 Tf 40 760 Td (Packing list: 3 pallets machine parts, 715 kg) Tj ET"
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"", b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    kids = []
    for n in range(scanned + 1):
        kids.append(f"{len(objs) + 1} 0 R".encode())
        page, content = len(objs) + 1, len(objs) + 2
        xobj = b"" if n == 0 else b"/XObject<</Im0 %d 0 R>>" % (page + 2)
        objs.append(b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents %d 0 R/Resources<</Font<</F1 3 0 R>>%s>>>>"
                    % (content, xobj))
        body = text if n == 0 else b"q 595 0 0 842 0 0 cm /Im0 Do Q"
        objs.append(b"<</Length %d>>stream\n%s\nendstream" % (len(body), body))
        if n:
            junk = bytes(range(256)) * 8
            objs.append(b"<</Type/XObject/Subtype/Image/Width 1240/Height 1754/BitsPerComponent 1/ColorSpace/DeviceGray"
                        b"/Filter%s/Length %d>>stream\n%s\nendstream" % (FILTERS[n % 3], len(junk), junk))
    objs[1] = b"<</Type/Pages/Kids[%s]/Count %d>>" % (b" ".join(kids), len(kids))
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, obj)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


@pytest.fixture
def scanner(monkeypatch):
    """The image model, mocked: what it was sent, and it finds the DG line on page 4."""
    seen = []
    monkeypatch.setattr(scans, "_done", {})
    monkeypatch.setattr(scans.llm, "chat_json", lambda name, system, user, *a, **k: (
        seen.append([part["type"] for part in user]), ({"text": "Page 4: Dangerous goods UN3480, Class 9"}, 0.0015))[1])
    return seen


def test_9_every_page_of_a_long_pdf_is_read(tmp_path, monkeypatch, scanner):
    pdf = _long_pdf(5)
    assert scans.needs_scan("PL.pdf", pdf, "Packing list: 3 pallets") and scans.scanned_pages(pdf) == [None] * 5
    box, api, _ = run(_case("PL.pdf", pdf), tmp_path, monkeypatch)
    assert scanner == [["file"]]  # the whole PDF, not page 1 only
    assert api.data["extracted"]["dangerous_goods"] is True and "UN3480" in api.data["extracted"]["dg_declared"]


def test_9_pages_we_cant_read_are_never_silent(tmp_path, monkeypatch, scanner):
    box, api, _ = run(_case("PL.pdf", _long_pdf(scans.MAX_PDF_PAGES + 2)), tmp_path, monkeypatch)
    assert scanner == []  # too long to send whole, and no JPEG page to cut out
    assert any("PL.pdf" in t and "not checked" in t for t in api.texts), api.texts


def test_9_core_facts_missing_and_pages_unread_asks_instead_of_quoting(tmp_path, monkeypatch, scanner):
    case = {**_case("PL.pdf", _long_pdf(scans.MAX_PDF_PAGES + 2), "Please quote, details in the attached PDF."),
            "raw": {"origin": None, "pieces": []}}
    box, api, _ = run(case, tmp_path, monkeypatch)
    assert "quote_sent" not in api.events and "error" not in api.events, api.texts
    assert any("not checked" in t for t in api.texts) and len(box.sent) <= 1  # at most the question, no amount


# ---- 12: an archive we can't open never lets the quote go out unchecked ----------------------------------------------
LOCKED = [
    ("docs.zip", _aes_zip({"packing_list.txt": b"UN3480 lithium ion batteries"})),
    ("docs.zip", _aes_zip({"packing_list.txt": b"UN3480", "readme.txt": b"Thanks for your business"},
                          open_files=["readme.txt"])),  # one open member must not hide the locked one
    ("docs.rar", b"Rar!\x1a\x07\x01\x00" + b"\x00\x13packing_list.xlsx\x00" + bytes(range(256)) * 4),
    ("docs.7z", b"7z\xbc\xaf\x27\x1c\x00\x04" + bytes(range(256)) * 4),
    ("docs.bin", b"Rar!\x1a\x07\x00" + b"\x00\x13packing_list.xlsx\x00" + bytes(range(256)) * 4),  # RAR by its bytes
]


@pytest.mark.parametrize("name,data", LOCKED, ids=["aes zip", "aes zip + open readme", "rar", "7z", "rar named .bin"])
def test_12_an_archive_we_cant_open_goes_to_a_person(name, data, tmp_path, monkeypatch):
    case = _case(name, data, BODY + " The archive password is Cargo2026.")
    box, api, _ = run(case, tmp_path, monkeypatch)
    assert box.sent == [] and "needs_human" in api.events and "quote_sent" not in api.events, api.texts
    assert any(name in t and "archive" in t.lower() for t in api.texts), api.texts


# ---- 13: an airline tariff that arrives as a photo --------------------------------------------------------------------
KIT = Path(__file__).resolve().parent.parent / "backend" / "data" / "start-kit"


class TariffApi:
    """The backend's real tariff parser (rows, or the error it logs as 'NOT read')."""

    def __init__(self):
        self.results = []

    def ingest_tariff(self, filename, content, sender):
        sys.path.insert(0, str(KIT.parent.parent))
        from ingest import parse_tariff
        try:
            sheet = parse_tariff(filename, base64.b64decode(content))
            result = {"rows": len(sheet["lanes"]), "airline": sheet["airline"]}
        except Exception as error:
            result = {"rows": 0, "error": str(error)}
        self.results.append((filename, result))
        return result


class TariffBox:
    def attachment(self, mail, attachment):
        return (KIT / "danube-wings-cargo-tariff-2026-11-p1.jpg").read_bytes()


TARIFF_MAIL = {"from": "tariffs@danube.example", "attachments": [{"filename": "danube-wings-cargo-tariff-2026-12.jpg"}]}


def test_13_a_photographed_tariff_is_transcribed_then_parsed(monkeypatch):
    typed = (KIT / "yellowtail-air-freight-tariff-2026-11.txt").read_text()  # what a good transcription looks like
    monkeypatch.setattr(scans, "read", lambda name, data, timeout=None: (typed, 0.0005))
    api = TariffApi()
    main._forward_tariff(TARIFF_MAIL, TariffBox(), api)
    (first, failed), (second, parsed) = api.results
    assert first.endswith(".jpg") and "image" in failed["error"]
    assert second.endswith(".jpg.ocr.txt") and parsed["rows"] > 0  # the name says the rates came from a photo


@pytest.mark.parametrize("ocr", ["", RuntimeError("gateway down")])
def test_13_an_unreadable_photo_stays_flagged_for_a_person(ocr, monkeypatch):
    def fake(name, data, timeout=None):
        if isinstance(ocr, Exception):
            raise ocr
        return ocr, 0.0005
    monkeypatch.setattr(scans, "read", fake)
    api = TariffApi()
    main._forward_tariff(TARIFF_MAIL, TariffBox(), api)
    assert api.results and all(r["rows"] == 0 and r["error"] for _, r in api.results)  # backend logs "NOT read"


def test_13_image_read_off_never_calls_the_model(monkeypatch):
    monkeypatch.setattr(scans, "IMAGE_READ", False)
    monkeypatch.setattr(scans, "read", lambda *a, **k: pytest.fail("no call"))
    api = TariffApi()
    main._forward_tariff(TARIFF_MAIL, TariffBox(), api)
    assert len(api.results) == 1 and "image" in api.results[0][1]["error"]


def test_12_a_plain_zip_still_quotes(tmp_path, monkeypatch):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        z.writestr("packing_list.txt", "3 pallets machine parts 715 kg")
    box, api, _ = run(_case("docs.zip", raw.getvalue()), tmp_path, monkeypatch)
    assert len(box.sent) == 1 and "needs_human" not in api.events, api.texts
