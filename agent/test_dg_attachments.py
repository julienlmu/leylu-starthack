import io
import re
import zipfile
import zlib

from attachments import dangerous_goods
from templates import quote_text


def xlsx(*cells: str) -> bytes:
    """A minimal xlsx whose shared strings hold the given cell texts (like round 10's PL_53839.xlsx)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", "<sst>" + "".join(f"<si><t>{c}</t></si>" for c in cells) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")
    return buf.getvalue()


class Box:
    def __init__(self, files: dict):
        self.files = files

    def attachment(self, mail, attachment):
        data = self.files[attachment["filename"]]
        if isinstance(data, Exception):
            raise data
        return data


def mail_with(*names):
    return {"id": 2261, "attachments": [{"id": i, "filename": n} for i, n in enumerate(names)]}


def test_packing_list_declares_dangerous_goods():
    box = Box({"PL_53839.xlsx": xlsx("Goods description:", "industrial adhesives", "Dangerous goods:",
                                     "UN1133, Class 3, Adhesives")})
    assert dangerous_goods(mail_with("PL_53839.xlsx"), box) == "UN1133, Class 3, Adhesives"


def test_no_un_number_no_dangerous_goods():
    box = Box({"PL.xlsx": xlsx("Dangerous goods:", "none"), "notes.txt": b"general cargo, non-dangerous"})
    assert dangerous_goods(mail_with("PL.xlsx", "notes.txt"), box) is None
    assert dangerous_goods({"id": 1}, box) is None  # no attachments at all


def test_unreadable_attachment_never_stops_the_quote():
    box = Box({"broken.xlsx": b"not a zip", "gone.csv": OSError("404"), "pl.csv": b"pcs;kg\n3;715\nUN 1993 Class 3"})
    assert dangerous_goods(mail_with("broken.xlsx", "gone.csv", "pl.csv"), box) == "UN 1993 Class 3"


RFQ = {"origin": "FRA", "destination": "GRU", "ask": "cheapest", "pickup": {"address": "61391 Bad Homburg"},
       "customer_reference": None, "commodity": "industrial adhesives", "language": "en",
       "pieces": [{"count": 3, "length_cm": 60, "width_cm": 100, "height_cm": 147, "weight_kg": 238.33}]}
OPTION = {"carrier": "Juniper Cargo Lines", "currency": "EUR", "total": 2481.5, "transit_days": 3}


def test_dangerous_goods_quote_asks_for_the_dg_papers_and_keeps_one_amount():
    body = quote_text({**RFQ, "dangerous_goods": True}, OPTION)
    assert "Shipper's Declaration for Dangerous Goods" in body and "MSDS" in body
    assert re.findall(r"\d[\d,.]*\.\d{2}", body) == ["2,481.50"]
    assert "Gefahrgut" in quote_text({**RFQ, "dangerous_goods": True, "language": "de"}, OPTION)


def test_general_cargo_quote_has_no_dg_line():
    assert "Dangerous Goods" not in quote_text({**RFQ, "dangerous_goods": False}, OPTION)


def pdf(*lines: str, compress: bool = False) -> bytes:
    """Build a minimal PDF content stream containing text (as in round 11's packing spec)."""
    content = b"BT /F1 10 Tf " + b" ".join(b"(" + l.encode("latin-1") + b") Tj" for l in lines) + b" ET"
    if compress:
        content = zlib.compress(content)
    filt = b" /Filter /FlateDecode" if compress else b""
    return (b"%PDF-1.4\n4 0 obj << /Length " + str(len(content)).encode() + filt + b" >>\nstream\n"
            + content + b"\nendstream\nendobj\n%%EOF")


def test_pdf_packing_spec_declares_dangerous_goods():
    for compress in (False, True):
        box = Box({"packing-spec_33955.pdf": pdf("Total gross weight (kg)", "855", "Dangerous goods:",
                                                  "UN1950, Class 2.1, Aerosols, flammable", compress=compress)})
        assert dangerous_goods(mail_with("packing-spec_33955.pdf"), box) == "UN1950, Class 2.1, Aerosols, flammable"
