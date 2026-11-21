"""A one-page PDF of our quote, for customers who ask for the offer as a PDF (round 76: rejected `no_pdf_offer`).

No packages: a minimal PDF 1.4 with Helvetica text lines, the same shape as the SLI PDFs 5U sends us. The amount is the
mail's amount, written once, so the PDF and the mail never disagree. Wire it in with `pdf_attachment(...)` as an entry
of the mailbox POST's `attachments` list.
"""
import base64
import re

PDF = re.compile(r"\bpdf\b", re.IGNORECASE)
OFFER = re.compile(r"\b(offer|quote|quotation|price|pricing|angebot|offerte|offre|devis|offerta|preventivo|oferta|"
                   r"cotizaci\w+|oferty|wycen\w+)\b", re.IGNORECASE)
# "please find our request for an air freight quotation attached, as a PDF file" (rounds 63, 75) is THEIR document
THEIRS = re.compile(r"\b(our|the)\s+(request|inquiry|enquiry|rfq|packing|sli|anfrage|demande|richiesta|solicitud)\b|"
                    r"\bfind\b[^.\n]{0,40}\battached\b", re.IGNORECASE)


def wants_pdf(text: str) -> bool:
    """The customer asks for OUR offer as a PDF ("Please attach your offer as a PDF to your reply", round 76): one
    sentence names a PDF and our offer/quote/price, and isn't about their own attached request or packing list."""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        if PDF.search(sentence) and OFFER.search(sentence) and not THEIRS.search(sentence):
            return True
    return False


def _escape(text: str) -> str:
    """PDF literal string: backslash and parentheses escaped; non-Latin-1 characters replaced (Helvetica/WinAnsi)."""
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return text.encode("cp1252", "replace").decode("cp1252")


def quote_pdf(lines: list[str], title: str = "Air freight quotation") -> bytes:
    """A one-page A4 PDF: a bold title, then one text line per entry (empty string = blank line)."""
    ops = [f"BT /F2 16 Tf 50 790 Td ({_escape(title)}) Tj ET"]
    y = 760
    for line in lines:
        if line:
            ops.append(f"BT /F1 10 Tf 50 {y} Td ({_escape(line)}) Tj ET")
        y -= 16
    stream = "\n".join(ops).encode("cp1252", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def quote_lines(rfq: dict, option: dict, reference: str, amount: str) -> list[str]:
    """The quote's facts, in English (the PDF is for filing; the mail itself is in the customer's language).
    `amount` is the exact amount string the mail states, e.g. "EUR 4,128.50"."""
    pieces = rfq.get("pieces") or []
    count = sum(p.get("count") or 1 for p in pieces)
    kg = sum((p.get("count") or 1) * (p.get("weight_kg") or 0) for p in pieces)
    pickup = (rfq.get("pickup") or {}).get("address")
    days = option.get("transit_days")
    lines = [
        f"Our reference: {reference}",
        f"Customer: {rfq['customer']}" if rfq.get("customer") else None,
        "",
        f"Route: {rfq.get('origin')} - {rfq.get('destination')}" + (f" (pickup: {pickup})" if pickup else ""),
        f"Goods: {count} piece{'s' if count != 1 else ''}"
        + (f" of {rfq['commodity']}" if rfq.get("commodity") else "") + f", {kg:.0f} kg gross",
        # no volume or other decimals: the price stays the only decimal number (one amount per mail and PDF)
        f"Ready date: {rfq.get('ready_date') or '-'}",
        f"Airline: {option.get('carrier') or '-'}",
        f"Transit time: about {max(1, round(days))} day{'s' if round(days) > 1 else ''}" if days else "Transit time: -",
        "",
        f"All-in price: {amount}",
        "Includes " + ("pickup, " if pickup else "") + "air freight, fuel and security surcharges.",
        "Subject to space on the flight, confirmed when we book.",
        "",
        "Leylü Air Freight - Lena Hartmann, Air Export",
    ]
    return [line for line in lines if line is not None]


def pdf_attachment(rfq: dict, option: dict, reference: str, amount: str) -> dict:
    """The mailbox POST attachment for this quote (5U allows pdf, max 10 MB)."""
    data = quote_pdf(quote_lines(rfq, option, reference, amount))
    safe = re.sub(r"[^A-Za-z0-9-]", "", reference) or "quote"
    return {"filename": f"Leylu-quote-{safe}.pdf", "content_type": "application/pdf",
            "content_base64": base64.b64encode(data).decode()}
