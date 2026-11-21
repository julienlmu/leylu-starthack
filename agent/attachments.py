"""Dangerous goods declared in an RFQ's attachments (packing lists). No LLM.

Round 10 (Sat 16:55) was rejected `dg_docs_missing`: the mail said "non-dangerous", the attached packing list
said "Dangerous goods: UN1133, Class 3, Adhesives". The attachment wins over the mail body.
"""
import io
import os
import re
import zipfile

UN_NUMBER = re.compile(r"\bUN\s?\d{4}\b")
# CARGO_WORDS_V2 (gate.py, same switch): exactly four digits ("Ref_UN-2024-118.pdf" is a reference), never right after
# ref / PO / invoice / Rechnung / Auftrag. Off: UN_NUMBER on the name with "_-." as spaces, as before.
CARGO_WORDS_V2 = os.environ.get("CARGO_WORDS_V2", "on").lower() != "off"
UN_V2 = re.compile(r"\bUN[\s-]?\d{4}\b(?![-/.]\d)")
REF_BEFORE = re.compile(r"\b(?:ref(?:erence)?|Referenz|Bezug|order|PO|purchase\s+order|invoice|Rechnung|Auftrag|"
                        r"Bestellung|Bestell)(?:s?(?:nummer|nr|no))?\.?\s*(?:no\.?|nr\.?|number|nummer|#)?\s*[:#._-]?\s*$",
                        re.I)


def _un(text: str) -> bool:
    if not CARGO_WORDS_V2:
        return bool(UN_NUMBER.search(text))
    return any(not REF_BEFORE.search(text[:m.start()].replace("_", " ")) for m in UN_V2.finditer(text))
DG_NAME = re.compile(r"\b(DGD|dangerous)\b", re.I)
NOT_DG_NAME = re.compile(r"\b(non|not|no)\b", re.I)  # "non_dangerous_goods_declaration.pdf"
ZIP_TEXT = ("xl/sharedStrings.xml", "xl/worksheets/", "word/document.xml")  # xlsx cells, docx body


def _texts(filename: str, data: bytes) -> list[str]:
    name = filename.lower()
    if name.endswith((".xlsx", ".docx")):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = " ".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.startswith(ZIP_TEXT))
        return re.findall(r"<(?:t|v)[^>]*>([^<]+)</(?:t|v)>", xml)
    if name.endswith((".csv", ".txt")):
        return data.decode("utf-8", "ignore").splitlines()
    if name.endswith(".xls"):  # old binary Excel: strings sit in the bytes (UTF-16 has a NUL after each letter)
        return [t.replace("\x00", "") for t in re.split(r"\x00{2,}|[\x01-\x08\x0b-\x1f]+", data.decode("latin-1"))]
    return []  # pdf is read by the backend, scans (images, PDFs without text) by scans.py: rfq_agent checks both


def dangerous_goods(mail: dict, box) -> str | None:
    """The first attachment line naming a UN number (e.g. "UN1133, Class 3, Adhesives"), or None."""
    for attachment in mail.get("attachments") or []:
        # "DGD_UN3480_lithium.pdf": the file name alone declares DG, even when its content can't be read
        name = re.sub(r"[_\-.]", " ", attachment.get("filename") or "")
        un_name = _un(re.sub(r"_", " ", attachment.get("filename") or "")) if CARGO_WORDS_V2 else UN_NUMBER.search(name)
        if un_name or (DG_NAME.search(name) and not NOT_DG_NAME.search(name)):
            return f"dangerous goods (attachment {attachment.get('filename')})"[:80]
        try:  # an unreadable attachment must never stop the quote
            texts = _texts(attachment.get("filename") or "", box.attachment(mail, attachment))
        except Exception as error:
            print(f"attachment {attachment.get('filename')} not readable: {error}")
            continue
        if hit := next((t.strip() for t in texts if _un(t)), None):
            return hit[:80]
    return None
