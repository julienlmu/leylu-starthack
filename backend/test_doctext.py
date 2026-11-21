"""Every document type an RFQ attachment may come in reaches the agent's DG / packing-list / constraint checks."""
import io
import zipfile
from email.message import EmailMessage

import pytest

from ingest import extract_lines

DG = "UN3480 Lithium ion batteries, Class 9, 120 kg"


def _zip(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buffer.getvalue()


ODT = _zip({"mimetype": "application/vnd.oasis.opendocument.text",
            "content.xml": f"<office:document-content><text:p>Packing list</text:p><text:p>{DG}</text:p>"
                           "</office:document-content>"})
ODS = _zip({"content.xml": "<table:table-row><table:table-cell><text:p>Item</text:p></table:table-cell>"
                           f"<table:table-cell><text:p>{DG}</text:p></table:table-cell></table:table-row>"})
PPTX = _zip({"ppt/slides/slide1.xml": f"<p:sld><a:p><a:r><a:t>{DG}</a:t></a:r></a:p></p:sld>"})
DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64 + DG.encode("utf-16-le") + b"\x00" * 32
XLS = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64 + DG.encode("latin-1") + b"\x00" * 32
RTF = ("{\\rtf1\\ansi{\\fonttbl{\\f0 Arial;}}\\f0 Packing list\\par " + DG + "\\par Gewicht 120 kg, Gr\\'f6\\'dfe}").encode()
HTML = f"<html><body><table><tr><td>Item</td><td>{DG}</td></tr></table><script>x=1</script></body></html>".encode()


def _eml(attachment_name="packing.odt", attachment=ODT) -> bytes:
    message = EmailMessage()
    message["From"], message["Subject"] = "shipper@example.com", "Fwd: packing list"
    message.set_content("Please see the packing list attached.")
    message.add_attachment(attachment, maintype="application", subtype="octet-stream", filename=attachment_name)
    return bytes(message)


@pytest.mark.parametrize("name,data", [
    ("packing.odt", ODT), ("packing.ods", ODS), ("slides.pptx", PPTX), ("packing.doc", DOC), ("list.xls", XLS),
    ("packing.rtf", RTF), ("packing.html", HTML), ("packing.htm", HTML), ("packing.xml", f"<r><i>{DG}</i></r>".encode()),
    ("packing.json", ('{"items": ["' + DG + '"]}').encode()), ("packing.tsv", f"Item\t{DG}".encode()),
    ("fwd.eml", _eml()), ("docs.zip", _zip({"inner/packing.odt": ODT, "notes.txt": "pickup Monday"})),
    ("NOEXTENSION", DOC),
])
def test_the_dg_line_is_read_from_every_document_type(name, data):
    text = "\n".join(extract_lines(name, data))
    assert "UN3480" in text and "Class 9" in text and "120 kg" in text


def test_rtf_umlauts_html_cells_and_scripts():
    assert "Größe" in "\n".join(extract_lines("x.rtf", RTF))
    html = extract_lines("x.html", HTML)
    assert any("Item | " + DG in line or ("Item" in line and DG in line) for line in html) and "x=1" not in "".join(html)


def test_a_zip_bomb_and_deep_nesting_are_not_unpacked():
    big = _zip({"a.txt": "0" * 21_000_000})
    assert extract_lines("big.zip", big) == []
    nested = _zip({"l1.zip": _zip({"l2.zip": _zip({"deep.txt": DG})})})
    assert "UN3480" not in "\n".join(extract_lines("nested.zip", nested))


def test_a_broken_file_inside_a_zip_never_loses_the_others():
    text = "\n".join(extract_lines("docs.zip", _zip({"broken.pdf": b"%PDF-garbage", "packing.rtf": RTF})))
    assert "UN3480" in text


def test_unknown_types_still_raise_for_tariffs():
    from ingest import TariffError
    with pytest.raises(TariffError):
        extract_lines("photo.heic", b"\x00\x01binary")


def test_an_excel_file_without_extension_is_read_as_excel():
    import openpyxl
    book = openpyxl.Workbook()
    book.active.append(["Item", DG])
    buffer = io.BytesIO()
    book.save(buffer)
    assert "UN3480" in "\n".join(extract_lines("attachment", buffer.getvalue()))
