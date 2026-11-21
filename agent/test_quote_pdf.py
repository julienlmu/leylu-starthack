import base64
import re

from quote_pdf import pdf_attachment, quote_pdf, wants_pdf

R76 = ("Please let me know the earliest possible arrival at DFW. \n\nPlease attach your offer as a PDF to your reply, "
       "as our purchasing department needs it for filing.")
RFQ = {"origin": "CGN", "destination": "DFW", "ready_date": "2026-11-28", "commodity": "automotive sensors",
       "pickup": {"address": "53345 Bonn, Germany"}, "volume_m3": 0.37,
       "pieces": [{"count": 5, "weight_kg": 13.0}]}
OPTION = {"carrier": "Lumen Air Cargo", "transit_days": 1.458}


def test_round_76_and_other_wordings_ask_for_a_pdf():
    assert wants_pdf(R76)
    for text in ("Could you send the quotation as PDF?", "Bitte senden Sie das Angebot als PDF.",
                 "Merci de nous envoyer votre offre en PDF.", "a PDF copy of the quote, please",
                 "Please attach the quote (PDF) for our records"):
        assert wants_pdf(text), text


def test_their_own_pdf_documents_are_not_a_pdf_request():
    for text in ("please find our request for an air freight quotation attached, as a PDF file (quotation-request.pdf). "
                 "It has all details of the shipment.",  # rounds 63 and 75
                 "Our packing list is attached as PDF.", "The SLI (pdf) is attached to this mail.",
                 "Please quote the fastest option to DFW.", ""):
        assert not wants_pdf(text), text


def test_the_pdf_is_valid_and_states_the_one_amount():
    att = pdf_attachment(RFQ, OPTION, "S-76", "EUR 408.55")
    assert att["content_type"] == "application/pdf" and att["filename"] == "Leylu-quote-S-76.pdf"
    data = base64.b64decode(att["content_base64"])
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert data.count(b"EUR 408.55") == 1 and len(re.findall(rb"\d[\d,]*\.\d\d", data)) == 1  # one amount only
    assert b"Lumen Air Cargo" in data and b"CGN - DFW" in data and b"65 kg" in data and b"about 1 day" in data
    xref = int(data.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    assert data[xref:xref + 4] == b"xref"  # the cross-reference offset is right, so readers open it


def test_parentheses_and_non_latin_text_cannot_break_the_pdf():
    data = quote_pdf(["Route: Köln (CGN) - 上海 (PVG)", "back\\slash"])
    assert b"K\xf6ln \\(CGN\\)" in data and b"back\\\\slash" in data and b"?? \\(PVG\\)" in data
