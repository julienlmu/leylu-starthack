"""Acceptance test for the next trap step: the DG line sits *inside* a file type we already read, in a part the reader
skips (a cell comment, a Word header, a PDF form field, a scanned second page, ...). Each file below is a normal packing
list plus one line "UN3480 Lithium ion batteries Class 9" in one hidden place. 13 of 14 are missed on main b2f118d;
those are strict xfails: when a reader learns the part, its test passes and the xfail mark must go.

Two are not the backend's job: the picture inside a docx and the scanned page 2 of a PDF are read by the agent's
scan reader (agent/scans.py, batu/scan-pages); here they only document that the text reader can't see them."""
import base64
import io
import zipfile

import docx
import openpyxl
import pytest
from openpyxl.comments import Comment
from PIL import Image, ImageDraw

from ingest import extract_lines

DG = "UN3480 Lithium ion batteries Class 9"
PACKING = "Packing list: 4 cartons, 120 kg"


def _xlsx(build) -> bytes:
    book = openpyxl.Workbook()
    build(book)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _docx(build) -> bytes:
    document = docx.Document()
    document.add_paragraph(PACKING)
    build(document)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _docx_xml(fragment: str) -> bytes:
    """A docx whose first paragraph gets `fragment` (raw WordprocessingML) appended."""
    source = zipfile.ZipFile(io.BytesIO(_docx(lambda d: None)))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "word/document.xml":
                data = data.decode().replace("</w:p>", fragment + "</w:p>", 1).encode()
            target.writestr(name, data)
    return out.getvalue()


def _picture(text: str, mode: str = "RGB") -> Image.Image:
    image = Image.new(mode, (300, 40), "white" if mode == "RGB" else 255)
    ImageDraw.Draw(image).text((5, 15), text, fill="black" if mode == "RGB" else 0)
    return image


def _pdf(objects: list[bytes]) -> bytes:
    body, offsets = b"%PDF-1.4\n", []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return body + f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()


def _stream(data: bytes, head: bytes = b"") -> bytes:
    return b"<<" + head + b"/Length %d>>stream\n" % len(data) + data + b"\nendstream"


TEXT = b"BT /F1 12 Tf 50 750 Td (Shippers Letter of Instruction: 4 cartons 120 kg) Tj ET"
FONT = b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"
PAGE = b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>"


def _comment(book):
    sheet = book.active
    sheet.append(["Item", "Qty", "kg"])
    sheet.append(["Battery packs", 4, 120])
    sheet["A2"].comment = Comment(DG, "shipper")


def _hidden_sheet(book):
    book.active.append(["Item", "kg"])
    hidden = book.create_sheet("DG")
    hidden.append([DG])
    hidden.sheet_state = "hidden"


def _formula(book):
    book.active.append(["Item"])
    book.active["A2"] = '="UN3480 "&"Lithium ion batteries Class 9"'  # written by a script: no cached value


def _header(document):
    document.sections[0].header.paragraphs[0].text = DG


def _footer(document):
    document.sections[0].footer.paragraphs[0].text = DG


def _nested_table(document):
    document.add_table(rows=1, cols=1).cell(0, 0).add_table(rows=1, cols=1).cell(0, 0).text = DG


def _word_picture(document):
    png = io.BytesIO()
    _picture(DG).save(png, "PNG")
    png.seek(0)
    document.add_picture(png)


GRAY = _picture(DG, "L").tobytes()
IMAGE_PAGE = b"q 300 0 0 40 50 600 cm /Im1 Do Q"

# The password is written in the mail ("the zip password is 1234"); built with `zip -P 1234`.
PASSWORD_ZIP = base64.b64decode(
    "UEsDBAoACQAAAI+2dV2ZnJW3MAAAACQAAAALABwAcGFja2luZy50eHRVVAkAA54SAmueEgJrdXgLAAEE9QEAAAQAAAAAwdQvGYLSkNaE0j/g/3zb"
    "namfxmG6Q5qrP9KLW02Qxo6axDefg98Nja8Bcl5jxZdcUEsHCJmclbcwAAAAJAAAAFBLAQIeAwoACQAAAI+2dV2ZnJW3MAAAACQAAAALABgAAAAA"
    "AAEAAACkgQAAAABwYWNraW5nLnR4dFVUBQADnhICa3V4CwABBPUBAAAEAAAAAFBLBQYAAAAAAQABAFEAAACFAAAAAAA=")

BACKEND = "backend reading task (Julien): not read on main yet"
SCAN = "agent scan reader (batu/scan-pages), not the text reader"

CASES = [
    ("xlsx_hidden_sheet.xlsx", lambda: _xlsx(_hidden_sheet), None),
    ("xlsx_comment.xlsx", lambda: _xlsx(_comment), BACKEND),
    ("xlsx_formula.xlsx", lambda: _xlsx(_formula), BACKEND),
    ("docx_header.docx", lambda: _docx(_header), BACKEND),
    ("docx_footer.docx", lambda: _docx(_footer), BACKEND),
    ("docx_nested_table.docx", lambda: _docx(_nested_table), BACKEND),
    ("docx_tracked_insert.docx", lambda: _docx_xml(
        f'<w:ins w:id="1" w:author="x" w:date="2026-11-21T00:00:00Z"><w:r><w:t>{DG}</w:t></w:r></w:ins>'), BACKEND),
    ("docx_textbox.docx", lambda: _docx_xml(
        '<w:r><w:pict><v:shape xmlns:v="urn:schemas-microsoft-com:vml"><v:textbox><w:txbxContent><w:p><w:r><w:t>'
        f'{DG}</w:t></w:r></w:p></w:txbxContent></v:textbox></v:shape></w:pict></w:r>'), BACKEND),
    ("docx_picture.docx", lambda: _docx(_word_picture), SCAN),
    ("pdf_form_field.pdf", lambda: _pdf([
        b"<</Type/Catalog/Pages 2 0 R/AcroForm<</Fields[6 0 R]>>>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        PAGE + b"/Annots[6 0 R]>>", _stream(TEXT), FONT,
        f"<</Type/Annot/Subtype/Widget/FT/Tx/T(dg)/V({DG})/Rect[50 700 400 720]/P 3 0 R>>".encode()]), BACKEND),
    ("pdf_annotation.pdf", lambda: _pdf([
        b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>", PAGE + b"/Annots[6 0 R]>>",
        _stream(TEXT), FONT, f"<</Type/Annot/Subtype/Text/Contents({DG})/Rect[50 700 70 720]>>".encode()]), BACKEND),
    ("pdf_embedded_file.pdf", lambda: _pdf([
        b"<</Type/Catalog/Pages 2 0 R/Names<</EmbeddedFiles<</Names[(pl.txt) 6 0 R]>>>>>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>", PAGE + b">>", _stream(TEXT), FONT,
        b"<</Type/Filespec/F(pl.txt)/EF<</F 7 0 R>>>>", _stream(DG.encode(), b"/Type/EmbeddedFile")]), BACKEND),
    ("pdf_mixed_scan_page2.pdf", lambda: _pdf([
        b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R 6 0 R]/Count 2>>", PAGE + b">>",
        _stream(TEXT), FONT,
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 7 0 R/Resources<</XObject<</Im1 8 0 R>>>>>>",
        _stream(IMAGE_PAGE),
        _stream(GRAY, b"/Type/XObject/Subtype/Image/Width 300/Height 40/ColorSpace/DeviceGray/BitsPerComponent 8")]),
     SCAN),
    ("zip_password.zip", lambda: PASSWORD_ZIP, BACKEND + " (password 1234 comes from the mail body)"),
]


@pytest.mark.parametrize("name, build, missing", [
    pytest.param(name, build, missing, id=name,
                 marks=[pytest.mark.xfail(strict=True, reason=missing)] if missing else [])
    for name, build, missing in CASES])
def test_dg_line_hidden_inside_the_file_is_read(name, build, missing):
    text = "\n".join(extract_lines(name, build()))
    assert "UN3480" in text, f"{name}: {text[:80]!r}"


@pytest.mark.parametrize("name, build", [(n, b) for n, b, _ in CASES], ids=[n for n, _, _ in CASES])
def test_the_visible_part_is_still_read(name, build):
    """Whatever the hidden part, the normal packing list next to it never gets lost (and nothing crashes)."""
    if name in ("zip_password.zip", "docx_nested_table.docx", "xlsx_formula.xlsx", "xlsx_hidden_sheet.xlsx"):
        pytest.skip("no visible packing line in this file")
    text = "\n".join(extract_lines(name, build()))
    assert "120 kg" in text or "120" in text
