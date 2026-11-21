"""R76 (no_pdf_offer): "Please attach your offer as a PDF". A one-page PDF of the quote (no new packages), and a CSV for
"as Excel/CSV". Exactly the amount string of the mail body, one amount only. OFFER_DOCS=off switches it off."""
import base64
import os
import re

OFFER_DOCS = os.environ.get("OFFER_DOCS", "on").lower() != "off"
PDF_ASK = re.compile(r"\b(?:as\s+an?\s+pdf|as\s+pdf|pdf\s+(?:attachment|file|document|format)|in\s+pdf|attach\w*\b[^.\n]{0,60}"
                     r"\bpdf\b|\bpdf\b[^.\n]{0,40}\battach\w*|als\s+pdf|im\s+pdf|pdf[- ]?(?:datei|anhang|dokument)|en\s+pdf|"
                     r"au\s+format\s+pdf|en\s+formato\s+pdf|in\s+formato\s+pdf|als\s+pdf-bestand)", re.I)
CSV_ASK = re.compile(r"\b(?:as\s+(?:an?\s+)?(?:excel|csv|spreadsheet|xlsx)|(?:excel|csv|xlsx)\s+(?:file|attachment|sheet)|"
                     r"als\s+(?:excel|csv)|en\s+(?:excel|csv))\b", re.I)


def wanted(text: str) -> str | None:
    """'pdf', 'csv' or None from the RFQ text (subject, body, attachments)."""
    if not OFFER_DOCS:
        return None
    if PDF_ASK.search(text or ""):
        return "pdf"
    if CSV_ASK.search(text or ""):
        return "csv"
    return None


def _esc(s: str) -> str:
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(lines: list[str]) -> bytes:
    """A minimal one-page A4 PDF, Helvetica, one line per entry."""
    content = ["BT", "/F1 16 Tf", "50 790 Td", f"({_esc(lines[0])}) Tj", "/F1 11 Tf"]
    for line in lines[1:]:
        content += ["0 -20 Td", f"({_esc(line)}) Tj"]
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def offer_lines(rfq: dict, option: dict) -> list[str]:
    count = sum(int(p.get("count") or 0) for p in rfq.get("pieces") or [])
    kg = sum(float(p.get("count") or 0) * float(p.get("weight_kg") or 0) for p in rfq.get("pieces") or [])
    pickup = (rfq.get("pickup") or {}).get("address")
    lines = ["Leylu Air Freight - Air freight offer",
             f"Customer: {rfq.get('contact_name') or ''}".strip(),
             f"Route: {rfq.get('origin')} to {rfq.get('destination')}" + (f", pickup at {pickup}" if pickup else ""),
             f"Shipment: {count} pieces, {kg:,.0f} kg" + (f", {rfq['volume_m3']:g} cbm" if rfq.get("volume_m3") else ""),
             f"Ready: {rfq.get('ready_date') or 'on request'}",
             f"Airline: {option.get('carrier') or ''}"]
    if option.get("transit_days"):
        lines.append(f"Transit: about {max(1, round(float(option['transit_days'])))} days")
    lines += [f"All-in price: {option['currency']} {float(option['total']):,.2f}",
              "Includes air freight, fuel and security" + (" and the truck pickup." if pickup else "."),
              "Valid for 7 days, subject to space at booking.", "Lena, Leylu Air Freight"]
    return lines


def attachment(kind: str, rfq: dict, option: dict, ref: str) -> dict | None:
    if kind == "pdf":
        data, ctype, ext = pdf(offer_lines(rfq, option)), "application/pdf", "pdf"
    elif kind == "csv":
        rows = [("field", "value")] + [tuple(l.split(": ", 1)) if ": " in l else ("note", l) for l in offer_lines(rfq, option)[1:]]
        data = "\n".join(";".join(f'"{c}"' for c in r) for r in rows).encode("utf-8")
        ctype, ext = "text/csv", "csv"
    else:
        return None
    return {"filename": f"Leylu-quote-{ref}.{ext}", "content_type": ctype, "content_base64": base64.b64encode(data).decode()}
