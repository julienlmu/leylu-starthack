"""The quote as a PDF attachment (round 75: rejected `no_pdf_offer`, the customer asked for the offer as a PDF).

The PDF carries exactly the text of the quote mail, so it states the same single amount. Standard library only: a plain
text PDF (Helvetica, WinAnsi), wrapped lines, as many A4 pages as needed. PDF_OFFER=always (default) attaches it to
every quote, `asked` only when the mail asks for a PDF, `off` never.
"""

import os
import re
import textwrap

PDF_OFFER = os.environ.get("PDF_OFFER", "always").lower()
ASKS_PDF = re.compile(r"\bpdf\b", re.I)  # "as a PDF", "als PDF", "en PDF", "PDF offer", "Angebot als PDF-Datei"
WIDTH, LINES_PER_PAGE = 90, 52


def wanted(mail: dict, attachment_texts=()) -> bool:
    if PDF_OFFER == "off":
        return False
    if PDF_OFFER != "asked":
        return True
    return bool(ASKS_PDF.search("\n".join([mail.get("subject") or "", mail.get("body") or "", *attachment_texts])))


def _escape(line: str) -> str:
    # WinAnsi covers Western European letters; anything else (CJK, Cyrillic) becomes "?" in the PDF only, the mail
    # body keeps it. The amount, currency, codes and references are ASCII and always survive.
    raw = line.encode("cp1252", errors="replace").decode("latin-1")
    return raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build(text: str, title: str = "Air freight quote") -> bytes:
    """A small, valid PDF of `text` (one or more A4 pages)."""
    lines = [title, ""]
    for paragraph in text.splitlines():
        lines += textwrap.wrap(paragraph, WIDTH) or [""]
    pages = [lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)] or [[]]
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for page in pages:
        stream = "BT /F1 11 Tf 14 TL 56 790 Td " + " ".join(f"({_escape(line)}) Tj T*" for line in page) + " ET"
        data = stream.encode("latin-1")
        objects.append(f"<< /Length {len(data)} >>\nstream\n{stream}\nendstream")
        content = len(objects)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {content} 0 R "
                       "/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
