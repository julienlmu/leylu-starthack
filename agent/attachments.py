"""Dangerous goods declared in an RFQ's attachments (packing lists). No LLM.

Round 10 (Sat 16:55) was rejected `dg_docs_missing`: the mail said "non-dangerous", the attached packing list
said "Dangerous goods: UN1133, Class 3, Adhesives". The attachment wins over the mail body.
"""
import io
import re
import zipfile

UN_NUMBER = re.compile(r"\bUN\s?\d{4}\b")
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
    return []  # shortcut: pdf/images not read here (the backend reads pdf); add OCR if a DG trap arrives as a scan


def dangerous_goods(mail: dict, box) -> str | None:
    """The first attachment line naming a UN number (e.g. "UN1133, Class 3, Adhesives"), or None."""
    for attachment in mail.get("attachments") or []:
        # "DGD_UN3480_lithium.pdf": the file name alone declares DG, even when its content can't be read
        name = re.sub(r"[_\-.]", " ", attachment.get("filename") or "")
        if UN_NUMBER.search(name) or (DG_NAME.search(name) and not NOT_DG_NAME.search(name)):
            return f"dangerous goods (attachment {attachment.get('filename')})"[:80]
        try:  # an unreadable attachment must never stop the quote
            texts = _texts(attachment.get("filename") or "", box.attachment(mail, attachment))
        except Exception as error:
            print(f"attachment {attachment.get('filename')} not readable: {error}")
            continue
        if hit := next((t.strip() for t in texts if UN_NUMBER.search(t)), None):
            return hit[:80]
    return None
