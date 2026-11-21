import base64

import offer_doc


def test_pdf_requests_are_recognised():
    for t in ("Please attach your offer as a PDF.", "Could you send the quotation as PDF attachment?",
              "Bitte senden Sie das Angebot als PDF.", "Merci d'envoyer votre offre en PDF."):
        assert offer_doc.wanted(t) == "pdf", t
    assert offer_doc.wanted("Please send your all-in price in EUR.") is None
    assert offer_doc.wanted("Please send it as an Excel file.") == "csv"


def test_the_pdf_is_a_pdf_with_the_one_amount():
    rfq = {"origin": "FRA", "destination": "PVG", "pieces": [{"count": 3, "weight_kg": 150}], "volume_m3": 1.2,
           "ready_date": "2026-11-27", "contact_name": "Li Wei", "pickup": None}
    doc = offer_doc.attachment("pdf", rfq, {"carrier": "Lumen Air Cargo", "currency": "EUR", "total": 2099.47,
                                            "transit_days": 3}, "123")
    data = base64.b64decode(doc["content_base64"])
    assert data.startswith(b"%PDF-1.4") and b"EUR 2,099.47" in data and data.rstrip().endswith(b"%%EOF")
    assert doc["filename"] == "Leylu-quote-123.pdf" and doc["content_type"] == "application/pdf"
