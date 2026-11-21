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


FORMATS = [("zip", r"\b(?:zip|archive|archiv|zipped|in\s+a\s+folder|in\s+einem\s+ordner|dans\s+un\s+dossier)\b"),
           ("docx", r"\b(?:word|docx|\.doc)\b"), ("xlsx", r"\b(?:excel|xlsx|spreadsheet|tabelle)\b"),
           ("csv", r"\bcsv\b"), ("txt", r"\b(?:txt|text\s+file|textdatei|plain\s+text)\b"), ("pdf", r"\bpdf\b")]
FILE_ASK = re.compile(r"\b(?:attach\w*|as\s+(?:an?\s+)?(?:file|document|attachment|pdf|word|docx|excel|xlsx|csv|txt|zip|"
                      r"zip\s+archive|archive|text\s+file|spreadsheet)|in\s+a\s+(?:folder|zip)|send\b[^.\n]{0,40}\b(?:file|document)|"
                      r"als\s+(?:datei|anhang|dokument)|im\s+anhang|en\s+pi[eè]ce\s+jointe|en\s+fichier|"
                      r"como\s+(?:archivo|adjunto)|in\s+allegato|come\s+file)\b", re.I)
FORM_ASK = re.compile(r"\b(?:our|the|unser\w*|notre|nuestro)\s+(?:attached\s+|enclosed\s+|beigefügte\w*\s+)?"
                      r"(?:form|formular|formulaire|formulario)\b", re.I)
NAME_ASK = re.compile(r"\b(?:name|call|nennen|benennen)\s+(?:the\s+|die\s+)?(?:file|datei)\s+"
                      r"(?:[\"“'‘]([^\"”'’\n]{2,80})[\"”'’]|(\S{3,80}))", re.I)
FOLDER_ASK = re.compile(r"\b(?:folder|ordner|dossier|directory)\s+(?:[\"“'‘]([^\"”'’\n]{2,40})[\"”'’]|([\w\-]{2,40}))", re.I)


def wanted(text: str) -> str | None:
    """The requested offer file format ('pdf', 'docx', 'xlsx', 'csv', 'txt', 'zip'), 'form' for "fill in our form"
    (a person), or None. A file asked for without a format is a PDF."""
    text = text or ""
    if not OFFER_DOCS:
        return None
    if FORM_ASK.search(text) and re.search(r"\b(?:fill|complete|ausfüllen|remplir|rellenar)\w*", text, re.I):
        return "form"
    asked = PDF_ASK.search(text) or CSV_ASK.search(text) or FILE_ASK.search(text)
    if not asked:
        return None
    window = text[max(0, asked.start() - 80): asked.end() + 80]
    for kind, pattern in FORMATS:
        if re.search(pattern, window, re.I):
            return kind
    return "pdf"


def safe_name(name: str, fallback: str) -> str:
    """Forward slashes only, no absolute paths, no '..', only letters, digits, '-', '_', '.' and '/'."""
    parts = [re.sub(r"[^\w.\-]", "_", p).strip("._") for p in (name or "").replace("\\", "/").split("/")]
    parts = [p for p in parts if p and p not in (".", "..")]
    return "/".join(parts) or fallback


def _esc(s: str) -> str:
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(lines: list[str]) -> bytes:
    """The offer as an A4 PDF: pdf_offer's writer (one PDF writer in the agent, checked with a real PDF reader)."""
    import pdf_offer
    return pdf_offer.build("\n".join(lines[1:]), title=lines[0])


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


def _docx(lines: list[str]) -> bytes:
    import io, zipfile
    from xml.sax.saxutils import escape
    body = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(l)}</w:t></w:r></w:p>" for l in lines)
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def _xlsx(lines: list[str]) -> bytes:
    import io, zipfile
    from xml.sax.saxutils import escape
    rows = []
    for i, line in enumerate(lines, 1):
        key, _, value = line.partition(": ")
        cells = [key, value] if value else [line]
        rows.append(f'<row r="{i}">' + "".join(
            f'<c r="{chr(65 + j)}{i}" t="inlineStr"><is><t>{escape(c)}</t></is></c>' for j, c in enumerate(cells)) + "</row>")
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Offer" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(rows) + "</sheetData></worksheet>"}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def attachment(kind: str, rfq: dict, option: dict, ref: str, request: str = "") -> dict | None:
    """The offer file the customer asked for; `request` (the RFQ text) may name the file or a folder."""
    import io, zipfile
    lines = offer_lines(rfq, option)
    base = f"Leylu-quote-{safe_name(str(ref), 'offer')}"
    named = NAME_ASK.search(request or "")
    folder = FOLDER_ASK.search(request or "")
    makers = {"pdf": (lambda: pdf(lines), "application/pdf"),
              "docx": (lambda: _docx(lines), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
              "xlsx": (lambda: _xlsx(lines), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
              "csv": (lambda: "\n".join(";".join(f'"{c}"' for c in (l.split(": ", 1) if ": " in l else ["note", l]))
                                           for l in lines[1:]).encode("utf-8"), "text/csv"),
              "txt": (lambda: "\n".join(lines).encode("utf-8"), "text/plain")}
    if kind == "zip":
        inner = safe_name(named.group(1) or named.group(2), base + ".pdf") if named else base + ".pdf"
        if "." not in inner.rsplit("/", 1)[-1]:
            inner += ".pdf"
        if folder:
            inner = safe_name(folder.group(1) or folder.group(2), "quote") + "/" + inner.rsplit("/", 1)[-1]
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(inner, pdf(lines))
        return {"filename": base + ".zip", "content_type": "application/zip",
                "content_base64": base64.b64encode(out.getvalue()).decode()}
    if kind not in makers:
        return None
    make, ctype = makers[kind]
    filename = base + "." + kind
    if named:
        wanted_name = safe_name(named.group(1) or named.group(2), filename).rsplit("/", 1)[-1]
        filename = wanted_name if wanted_name.lower().endswith("." + kind) else wanted_name + "." + kind
    return {"filename": filename, "content_type": ctype, "content_base64": base64.b64encode(make()).decode()}
