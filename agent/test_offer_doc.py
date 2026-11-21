import base64

import offer_doc


def test_pdf_requests_are_recognised():
    for t in ("Please attach your offer as a PDF.", "Could you send the quotation as PDF attachment?",
              "Bitte senden Sie das Angebot als PDF.", "Merci d'envoyer votre offre en PDF."):
        assert offer_doc.wanted(t) == "pdf", t
    assert offer_doc.wanted("Please send your all-in price in EUR.") is None
    assert offer_doc.wanted("Please send it as an Excel file.") == "xlsx"


def test_the_pdf_is_a_pdf_with_the_one_amount():
    rfq = {"origin": "FRA", "destination": "PVG", "pieces": [{"count": 3, "weight_kg": 150}], "volume_m3": 1.2,
           "ready_date": "2026-11-27", "contact_name": "Li Wei", "pickup": None}
    doc = offer_doc.attachment("pdf", rfq, {"carrier": "Lumen Air Cargo", "currency": "EUR", "total": 2099.47,
                                            "transit_days": 3}, "123")
    data = base64.b64decode(doc["content_base64"])
    assert data.startswith(b"%PDF-1.4") and b"EUR 2,099.47" in data and data.rstrip().endswith(b"%%EOF")
    assert doc["filename"] == "Leylu-quote-123.pdf" and doc["content_type"] == "application/pdf"


import io
import zipfile

RFQ = {"origin": "FRA", "destination": "PVG", "pieces": [{"count": 3, "weight_kg": 150}], "ready_date": "2026-11-27"}
OPT = {"carrier": "Lumen Air Cargo", "currency": "EUR", "total": 2099.47, "transit_days": 3}


def test_every_format_opens_and_holds_the_amount():
    for kind, text in (("docx", "Please send the offer as a Word document."), ("xlsx", "Attach the quote as Excel file."),
                       ("csv", "Please send it as a CSV file."), ("txt", "Send the offer as a text file please."),
                       ("zip", "Please send the offer as a zip archive."), ("pdf", "Please attach the offer as a file.")):
        assert offer_doc.wanted(text) == kind, text
        doc = offer_doc.attachment(kind, RFQ, OPT, "77")
        data = base64.b64decode(doc["content_base64"])
        if kind in ("docx", "xlsx", "zip"):
            z = zipfile.ZipFile(io.BytesIO(data))
            assert any(b"2,099.47" in z.read(n) for n in z.namelist()), kind
        else:
            assert b"2,099.47" in data, kind
    assert offer_doc.wanted("Please fill in our attached form with your rates.") == "form"


def test_folder_and_file_names_are_safe():
    req = 'Please send it as a zip, put it in a folder "quotes" and name the file "../../etc/Offer Lima.pdf".'
    doc = offer_doc.attachment("zip", RFQ, OPT, "77", req)
    names = zipfile.ZipFile(io.BytesIO(base64.b64decode(doc["content_base64"]))).namelist()
    assert names == ["quotes/Offer_Lima.pdf"]
    assert all(not n.startswith("/") and ".." not in n for n in names)
    doc = offer_doc.attachment("zip", RFQ, OPT, "77", 'As a zip, name the file "evil.exe".')
    assert zipfile.ZipFile(io.BytesIO(base64.b64decode(doc["content_base64"]))).namelist() == ["evil.exe.pdf"]
