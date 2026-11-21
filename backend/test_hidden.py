"""The DG line hidden inside a file type we already read, in a part a page-text reader skips (Batu's probe): Word
headers / footers / text boxes / nested tables / tracked inserts / comments / footnotes, PDF form fields / notes /
embedded files, Excel comments / uncached formulas, PowerPoint notes / comments, and password-protected zip / PDF
with the password in the mail. Every probe file is built here; each is checked in extract_lines and the endpoint."""
import base64
import hashlib
import io
import struct
import zipfile
import zlib

import docx
import openpyxl
import pytest
from fastapi.testclient import TestClient
from openpyxl.comments import Comment

from app import create_app
from crm import Crm
from ingest import extract_lines

DG = "UN3480 Lithium ion batteries Class 9"
PACKING = ["Packing list", "3 pallets, 450 kg gross", "Machine parts, not restricted"]
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _rezip(data: bytes, replace: dict) -> bytes:
    """A copy of the zip with some parts replaced or added."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            if name not in replace:
                dst.writestr(name, src.read(name))
        for name, part in replace.items():
            dst.writestr(name, part)
    return out.getvalue()


def _docx(where: str) -> bytes:
    document = docx.Document()
    for line in PACKING:
        document.add_paragraph(line)
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Item", "Weight"
    if where == "header":
        document.sections[0].header.paragraphs[0].text = DG
    elif where == "footer":
        document.sections[0].footer.paragraphs[0].text = DG
    elif where == "nested table":
        table.cell(1, 0).add_table(rows=1, cols=2).cell(0, 1).text = DG
    buffer = io.BytesIO()
    document.save(buffer)
    data = buffer.getvalue()
    body = {
        "text box": '<w:p><w:r><mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/'
                    '2006"><mc:Choice Requires="wps"><w:drawing><w:txbxContent><w:p><w:r><w:t>' + DG + '</w:t></w:r>'
                    '</w:p></w:txbxContent></w:drawing></mc:Choice><mc:Fallback><w:pict><w:txbxContent><w:p><w:r><w:t>'
                    + DG + '</w:t></w:r></w:p></w:txbxContent></w:pict></mc:Fallback></mc:AlternateContent></w:r></w:p>',
        "tracked insert": '<w:p><w:ins w:id="1" w:author="Shipper"><w:r><w:t xml:space="preserve">' + DG +
                          '</w:t></w:r></w:ins></w:p><w:p><w:del w:id="2" w:author="Shipper"><w:r><w:delText>UN1845 '
                          'dry ice deleted</w:delText></w:r></w:del></w:p>',
    }.get(where)
    if body:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode()
        return _rezip(data, {"word/document.xml": xml.replace("<w:sectPr", body + "<w:sectPr", 1)})
    part = {"comment": "comments", "footnote": "footnotes", "endnote": "endnotes"}.get(where)
    if part:
        tag = part[:-1]
        return _rezip(data, {f"word/{part}.xml": f'<w:{part} {W}><w:{tag} w:id="1"><w:p><w:r><w:t>{DG}</w:t></w:r>'
                                                 f'</w:p></w:{tag}></w:{part}>'})
    return data


def _xlsx(where: str) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    for row in (["Item", "Weight"], ["Machine parts", 450]):
        sheet.append(row)
    if where == "comment":
        sheet["A2"].comment = Comment(DG, "Shipper")
    else:  # written by a script: a formula and no cached value
        sheet["A3"] = f'="{DG}"'
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


PPT = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" ' \
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
SLIDE = f"<p:sld {PPT}><a:p><a:r><a:t>Packing list</a:t></a:r></a:p><a:p><a:r><a:t>3 pallets</a:t></a:r></a:p></p:sld>"


def _pptx(where: str) -> bytes:
    hidden = {"notes": ("ppt/notesSlides/notesSlide1.xml", f"<p:notes {PPT}><a:p><a:r><a:t>{DG}</a:t></a:r></a:p></p:notes>"),
              "comment": ("ppt/comments/comment1.xml", f"<p:cmLst {PPT}><p:cm authorId=\"0\"><p:text>{DG}</p:text>"
                                                        "</p:cm></p:cmLst>"),
              "modern comment": ("ppt/comments/modernComment_100_1.xml",
                                 f"<p188:cmLst {PPT}><p188:cm><p188:txBody><a:p><a:r><a:t>{DG}</a:t></a:r></a:p>"
                                 "</p188:txBody></p188:cm></p188:cmLst>")}[where]
    return _rezip(_rezip(b"PK\x05\x06" + b"\x00" * 18, {}), {"ppt/slides/slide1.xml": SLIDE, hidden[0]: hidden[1]})


def _rc4(key: bytes, data: bytes) -> bytes:
    s, j, out = list(range(256)), 0, bytearray()
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(byte ^ s[(s[i] + s[j]) % 256])
    return bytes(out)


PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")


def _pdf(text: str = "Packing list: 3 pallets, 450 kg gross", field=None, note=None, embedded=None, attached=None,
         password=None, pages: int = 1) -> bytes:
    """A PDF written by hand: page text, plus an optional filled form field, sticky note, embedded file (name tree),
    file-attachment note, or RC4-40 encryption with a user password (streams only: no strings when encrypted)."""
    objs = {1: "<< /Type /Catalog /Pages 2 0 R{acro}{names} >>", 2: "", 6: "<< /Type /Font /Subtype /Type1 "
            "/BaseFont /Helvetica >>"}
    streams, annots = {}, []
    kids = []
    for n in range(pages):
        page, content = 100 + 2 * n, 101 + 2 * n
        kids.append(f"{page} 0 R")
        objs[page] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R "
                      "/Resources << /Font << /F1 6 0 R >> >>{annots} >>")
        lines = [text] if pages == 1 else [f"Line {n}-{i}: machine parts, carton {i}, 12 kg" for i in range(40)]
        streams[content] = ("<< >>", ("BT /F1 10 Tf 40 760 Td 12 TL " + " ".join(f"({t}) Tj T*" for t in lines)
                                      + " ET").encode())
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>"
    acro = names = ""
    if field:
        objs[5] = f"<< /Type /Annot /Subtype /Widget /FT /Tx /T (dangerous_goods) /V ({field}) /Rect [40 600 300 620] >>"
        annots.append("5 0 R")
        acro = " /AcroForm << /Fields [5 0 R] >>"
    if note:
        objs[9] = f"<< /Type /Annot /Subtype /Text /Contents ({note}) /Rect [40 500 60 520] >>"
        annots.append("9 0 R")
    if embedded:
        objs[7] = "<< /Type /Filespec /F (packing.txt) /UF (packing.txt) /EF << /F 8 0 R >> >>"
        streams[8] = ("<< /Type /EmbeddedFile >>", embedded)
        names = " /Names << /EmbeddedFiles << /Names [(packing.txt) 7 0 R] >> >>"
    if attached:
        objs[10] = "<< /Type /Annot /Subtype /FileAttachment /FS 11 0 R /Rect [40 400 60 420] >>"
        objs[11] = "<< /Type /Filespec /F (sli.docx) /EF << /F 12 0 R >> >>"
        streams[12] = ("<< /Type /EmbeddedFile >>", attached)
        annots.append("10 0 R")
    objs[1] = objs[1].format(acro=acro, names=names)
    for page in (100 + 2 * n for n in range(pages)):
        objs[page] = objs[page].format(annots=f" /Annots [{' '.join(annots)}]" if annots and page == 100 else "")
    file_id, trailer_extra, key = b"0123456789abcdef", "", None
    if password is not None:
        def pad(p: str) -> bytes:
            return (p.encode() + PAD)[:32]
        owner = _rc4(hashlib.md5(pad("owner")).digest()[:5], pad(password))
        key = hashlib.md5(pad(password) + owner + struct.pack("<i", -4) + file_id).digest()[:5]
        objs[20] = f"<< /Filter /Standard /V 1 /R 2 /O <{owner.hex()}> /U <{_rc4(key, PAD).hex()}> /P -4 >>"
        trailer_extra = " /Encrypt 20 0 R"
    out, offsets = bytearray(b"%PDF-1.4\n"), {}
    for num in sorted({**objs, **streams}):
        offsets[num] = len(out)
        if num in streams:
            head, data = streams[num]
            if key:
                data = _rc4(hashlib.md5(key + num.to_bytes(3, "little") + b"\x00\x00").digest()[:10], data)
            out += f"{num} 0 obj\n{head[:-2]}/Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream\nendobj\n"
        else:
            out += f"{num} 0 obj\n{objs[num]}\nendobj\n".encode()
    xref, size = len(out), max(offsets) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offsets[n]:010d} 00000 n \n".encode() if n in offsets else b"0000000000 65535 f \n"
                    for n in range(1, size))
    out += (f"trailer\n<< /Size {size} /Root 1 0 R /ID [<{file_id.hex()}> <{file_id.hex()}>]{trailer_extra} >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


def _zipcrypto(files: dict, password: str, unencrypted=()) -> bytes:
    """A ZipCrypto-encrypted zip (stored; `unencrypted` names stay open), which zipfile can read but not write."""
    out, central = bytearray(), bytearray()
    for name, data in files.items():
        keys = [0x12345678, 0x23456789, 0x34567890]

        def update(c: int):
            keys[0] = zlib.crc32(bytes([c]), keys[0] ^ 0xFFFFFFFF) ^ 0xFFFFFFFF
            keys[1] = ((keys[1] + (keys[0] & 0xFF)) * 134775813 + 1) & 0xFFFFFFFF
            keys[2] = zlib.crc32(bytes([keys[1] >> 24]), keys[2] ^ 0xFFFFFFFF) ^ 0xFFFFFFFF

        for c in password.encode():
            update(c)
        crc, secret = zlib.crc32(data), bytearray()
        for c in bytes(11) + bytes([crc >> 24]) + data:
            t = (keys[2] | 2) & 0xFFFF
            secret.append(c ^ (((t * (t ^ 1)) >> 8) & 0xFF))
            update(c)
        locked = name not in unencrypted
        secret = secret if locked else data
        fields = (20, int(locked), 0, 0, 0x21, crc, len(secret), len(data), len(name), 0)
        offset = len(out)
        out += struct.pack("<4s5H3I2H", b"PK\x03\x04", *fields) + name.encode() + secret
        central += struct.pack("<4s6H3I5H2I", b"PK\x01\x02", 20, *fields, 0, 0, 0, 0, offset) + name.encode()
    end = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, len(files), len(files), len(central), len(out), 0)
    return bytes(out + central + end)


def _aes_zip() -> bytes:
    """A zip whose entry claims WinZip AES (method 99, encrypted flag): never decrypted."""
    data = bytearray(_rezip(b"PK\x05\x06" + b"\x00" * 18, {"packing.txt": DG}))
    for start, flag in ((data.find(b"PK\x03\x04"), 6), (data.find(b"PK\x01\x02"), 8)):
        struct.pack_into("<2H", data, start + flag, 1, 99)
    return bytes(data)


PROBES = [
    *((f"docx {w}", "packing.docx", _docx(w)) for w in ("header", "footer", "text box", "nested table",
                                                         "tracked insert", "comment", "footnote", "endnote")),
    ("pdf form field (fillable SLI)", "sli.pdf", _pdf(field=DG)),
    ("pdf sticky note", "packing.pdf", _pdf(note=DG)),
    ("pdf embedded file", "packing.pdf", _pdf(embedded=f"Packing list\n{DG}".encode())),
    ("pdf file-attachment note (docx in it)", "packing.pdf", _pdf(attached=_docx("header"))),
    ("xlsx cell comment", "packing.xlsx", _xlsx("comment")),
    ("xlsx formula without cached value", "packing.xlsx", _xlsx("formula")),
    ("xlsm formula without cached value", "packing.xlsm", _xlsx("formula")),
    *((f"pptx {w}", "slides.pptx", _pptx(w)) for w in ("notes", "comment", "modern comment")),
]
LOCKED = [  # (case, filename, bytes, hints)
    ("zip, ZipCrypto, password in mail", "docs.zip", _zipcrypto({"packing.txt": f"Packing list\n{DG}".encode()},
                                                                 "Fr8-2026"), ["wrong", "Fr8-2026"]),
    ("pdf, RC4, password in mail", "packing.pdf", _pdf(text=DG, password="geheim42"), ["geheim42"]),
    ("zip with a locked pdf inside", "docs.zip",
     _zipcrypto({"packing.pdf": _pdf(text=DG, password="pw1")}, "pw1"), ["pw1"]),
]


def _endpoint(name: str, data: bytes, hints=None) -> dict:
    body = {"filename": name, "content_base64": base64.b64encode(data).decode()}
    if hints is not None:
        body["password_hints"] = hints
    return TestClient(create_app(Crm(":memory:"), None)).post("/api/attachments/text", json=body).json()


@pytest.mark.parametrize("case,name,data", PROBES, ids=[p[0] for p in PROBES])
def test_the_hidden_dg_line_is_read(case, name, data):
    assert DG in "\n".join(extract_lines(name, data)), case
    assert DG in _endpoint(name, data)["text"], case


@pytest.mark.parametrize("case,name,data,hints", LOCKED, ids=[p[0] for p in LOCKED])
def test_a_password_from_the_mail_opens_the_file(case, name, data, hints):
    assert DG in "\n".join(extract_lines(name, data, passwords=hints))
    assert DG in _endpoint(name, data, hints)["text"]
    locked = _endpoint(name, data)  # no hint: nothing read, and the reason says why
    assert locked["text"] == "" and "password" in locked["error"]


def test_word_reading_order_rows_and_deleted_text():
    lines = extract_lines("x.docx", _docx("tracked insert"))
    assert lines[:3] == PACKING and "Item | Weight" in lines and not any("UN1845" in line for line in lines)
    text_box = extract_lines("x.docx", _docx("text box"))
    assert sum(DG in line for line in text_box) == 1  # the text box's VML fallback copy is not read twice


def test_pdf_form_field_keeps_its_name_and_page_text_comes_first():
    lines = extract_lines("sli.pdf", _pdf(field=DG))
    assert lines[0].startswith("Packing list") and f"dangerous_goods: {DG}" in lines


def test_an_aes_zip_says_it_is_not_supported():
    error = _endpoint("docs.zip", _aes_zip(), ["anything"])["error"]
    assert "AES" in error


def test_a_mixed_zip_reads_the_open_file_and_names_the_locked_one():
    data = _zipcrypto({"locked.txt": b"secret", "open.txt": DG.encode()}, "x", unencrypted=["open.txt"])
    text = "\n".join(extract_lines("docs.zip", data))
    assert DG in text and "locked.txt: password-protected, not read" in text


def test_a_large_pdf_stays_fast():
    import time
    data = _pdf(pages=200, field=DG)
    start = time.monotonic()
    lines = extract_lines("big.pdf", data)
    assert f"dangerous_goods: {DG}" in lines and len(lines) > 8000
    assert time.monotonic() - start < 30
