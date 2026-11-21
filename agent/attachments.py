"""Dangerous goods declared in an RFQ's attachments (packing lists). No LLM.

Round 10 (Sat 16:55) was rejected `dg_docs_missing`: the mail said "non-dangerous", the attached packing list
said "Dangerous goods: UN1133, Class 3, Adhesives". The attachment wins over the mail body.
"""
import io
import re
import zipfile

UN_NUMBER = re.compile(r"\bUN\s?\d{4}\b")
ZIP_TEXT = ("xl/sharedStrings.xml", "xl/worksheets/", "word/document.xml")  # xlsx cells, docx body


def _texts(filename: str, data: bytes) -> list[str]:
    name = filename.lower()
    if name.endswith((".xlsx", ".docx")):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = " ".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.startswith(ZIP_TEXT))
        return re.findall(r"<(?:t|v)[^>]*>([^<]+)</(?:t|v)>", xml)
    if name.endswith((".csv", ".txt")):
        return data.decode("utf-8", "ignore").splitlines()
    return []  # shortcut: pdf/xls/images not read; add pdfplumber if a DG trap arrives as pdf


def dangerous_goods(mail: dict, box) -> str | None:
    """The first attachment line naming a UN number (e.g. "UN1133, Class 3, Adhesives"), or None."""
    for attachment in mail.get("attachments") or []:
        try:  # an unreadable attachment must never stop the quote
            texts = _texts(attachment.get("filename") or "", box.attachment(mail, attachment))
        except Exception as error:
            print(f"attachment {attachment.get('filename')} not readable: {error}")
            continue
        if hit := next((t.strip() for t in texts if UN_NUMBER.search(t)), None):
            return hit[:80]
    return None
