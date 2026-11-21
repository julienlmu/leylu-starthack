"""Attachment traps 5U may send next (sweep of Sun 00:15): a DG line in a Word chart / SmartArt, in PDF form fields
(AcroForm, XFA) or rich-text notes, an archive we can't open, a photographed tariff. Files built here, stdlib only."""

import io
import zipfile

import docx
import pytest

from ingest import extract_lines
from test_doctext_probe import FONT, TEXT, _pdf, _stream


def _docx_with(parts: dict) -> bytes:
    d = docx.Document()
    d.add_paragraph("Packing list")
    raw = io.BytesIO()
    d.save(raw)
    src, out = zipfile.ZipFile(io.BytesIO(raw.getvalue())), io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for info in src.infolist():
            z.writestr(info, src.read(info))
        for name, xml in parts.items():
            z.writestr(name, xml)
    return out.getvalue()


CHART = ('<c:chartSpace xmlns:c="c" xmlns:a="a"><c:chart><c:title><c:tx><c:rich><a:p><a:r><a:t>Shipment mix'
         '</a:t></a:r></a:p></c:rich></c:tx></c:title><c:ser><c:tx><c:strRef><c:strCache><c:pt idx="0">'
         '<c:v>UN3480 Lithium ion batteries</c:v></c:pt></c:strCache></c:strRef></c:tx></c:ser></c:chart></c:chartSpace>')
SMARTART = ('<dgm:dataModel xmlns:dgm="d" xmlns:a="a"><dgm:ptLst><dgm:pt><dgm:t><a:p><a:r><a:t>Class 3 UN1263 Paint'
            '</a:t></a:r></a:p></dgm:t></dgm:pt></dgm:ptLst></dgm:dataModel>')


# ---- 10: DG only in a Word chart or SmartArt diagram -----------------------------------------------------------------
def test_10_dg_in_a_word_chart_is_read():
    assert any("UN3480" in line for line in extract_lines("pl.docx", _docx_with({"word/charts/chart1.xml": CHART})))


def test_10_dg_in_a_smartart_diagram_is_read():
    lines = extract_lines("pl.docx", _docx_with({"word/diagrams/data1.xml": SMARTART}))
    assert any("UN1263" in line for line in lines)


# ---- 11: DG only in PDF form data (AcroForm /V, XFA) or a rich-text note (/RC) ---------------------------------------
XFA = (b'<xdp:xdp xmlns:xdp="http://ns.adobe.com/xdp/"><xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">'
       b'<xfa:data><sli><cargo>machine parts</cargo><dg_declaration>UN3481 Lithium ion batteries packed with equipment'
       b'</dg_declaration></sli></xfa:data></xfa:datasets></xdp:xdp>')


def _pdf_with(catalog_extra: bytes = b"", annot: bytes | None = None, extra=()) -> bytes:
    page = b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>" + \
        (b"/Annots[6 0 R]" if annot else b"") + b">>"
    return _pdf([b"<</Type/Catalog/Pages 2 0 R" + catalog_extra + b">>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>", page,
                 _stream(TEXT), FONT, annot or b"<<>>", *extra])


@pytest.mark.parametrize("xfa", [b"7 0 R", b"[(template) 8 0 R (datasets) 7 0 R]"])
def test_11_dg_in_xfa_form_data_is_read(xfa):
    pdf = _pdf_with(b"/AcroForm<</Fields[]/XFA " + xfa + b">>", extra=[_stream(XFA), _stream(b"<template/>")])
    assert any("UN3481" in line for line in extract_lines("sli.pdf", pdf))


def test_11_dg_in_a_rich_text_note_without_contents_is_read():
    rc = b'(<body xmlns="http://www.w3.org/1999/xhtml"><p>Contains <b>UN3090</b> lithium metal cells</p></body>)'
    pdf = _pdf_with(annot=b"<</Type/Annot/Subtype/FreeText/Rect[40 500 300 520]/RC" + rc + b">>")
    assert any("UN3090 lithium" in line for line in extract_lines("sli.pdf", pdf))


def test_11_dg_in_a_form_field_value_is_read():
    field = b"<</Type/Annot/Subtype/Widget/FT/Tx/T(dg)/V(UN1845 Dry ice 20 kg)/Rect[40 600 300 620]>>"
    pdf = _pdf_with(b"/AcroForm<</Fields[6 0 R]>>", annot=field)
    assert "dg: UN1845 Dry ice 20 kg" in extract_lines("sli.pdf", pdf)
