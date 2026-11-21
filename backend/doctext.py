"""Text from the document types ingest.extract_lines doesn't read itself: old Office (.doc, .xls, .msg), OpenDocument
(.odt, .ods, .odp), .pptx, .rtf, .html, .xml, .json, .tsv, .eml (with its attachments) and .zip (each file inside).
Standard library only, no LLM: the agent's DG, packing-list and constraint checks then read these like a PDF.
A file with no or a wrong extension is recognised by its first bytes.
"""

import email
import html
import io
import json
import re
import zipfile
from email import policy

MAX_ZIP_FILES, MAX_ZIP_BYTES = 20, 20_000_000  # a zip bomb never gets unpacked
OFFICE_XML = {"word/document.xml", "word/header", "word/footer", "ppt/slides/slide", "ppt/notesSlides/",
              "xl/sharedStrings.xml", "xl/worksheets/sheet", "content.xml"}


def lines(filename: str, content: bytes, read=None, depth: int = 0) -> list[str] | None:
    """The file as text lines, or None for a type this module doesn't know. `read(name, bytes)` reads a file found
    inside a zip or an e-mail (ingest.extract_lines, so a PDF inside a zip is read too)."""
    name = filename.lower()
    kind = name.rsplit(".", 1)[-1] if "." in name else _sniff(content)
    if kind in ("doc", "xls", "msg", "ole"):
        return _ole_strings(content)
    if kind in ("odt", "ods", "odp", "pptx", "zip-office"):
        return _office_xml(content)
    if kind == "rtf":
        return _rtf(content.decode("latin-1", "replace"))
    if kind in ("html", "htm", "xhtml", "xml"):
        return _markup(content.decode("utf-8", "replace"))
    if kind == "json":
        return _json(content)
    if kind in ("tsv", "tab"):
        return [" | ".join(row.split("\t")) for row in content.decode("utf-8", "replace").splitlines()]
    if kind == "eml":
        return _eml(content, read, depth)
    if kind == "zip":
        return _zip(content, read, depth)
    if kind in ("md", "log", "text"):
        return content.decode("utf-8", "replace").splitlines()
    return None


def _sniff(content: bytes) -> str:
    """The type from the first bytes, for an attachment without (or with a wrong) extension."""
    head = content[:8]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "ole"  # .doc / .xls / .msg
    if head.startswith(b"PK"):
        try:
            names = zipfile.ZipFile(io.BytesIO(content)).namelist()
        except zipfile.BadZipFile:
            return ""
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
        return "zip-office" if "content.xml" in names or any(n.startswith("ppt/") for n in names) else "zip"
    if head.startswith(b"{\\rtf"):
        return "rtf"
    text = content[:500].decode("utf-8", "ignore").lstrip().lower()
    if text.startswith(("<!doctype html", "<html", "<?xml")):
        return "html"
    if re.match(r"(?:from|received|return-path|message-id|subject|mime-version):", text):
        return "eml"
    return ""


def _ole_strings(content: bytes) -> list[str]:
    """Old binary Office (.doc, .xls, .msg): the text sits in the bytes as UTF-16 or single-byte runs."""
    found = re.findall(rb"(?:[\x20-\x7e\xa0-\xff]\x00){4,}", content)
    texts = [chunk.decode("utf-16-le", "ignore") for chunk in found]
    texts += [chunk.decode("latin-1") for chunk in re.findall(rb"[\x20-\x7e\xc0-\xff]{6,}", content)]
    return [t.strip() for t in dict.fromkeys(texts) if re.search(r"[A-Za-zÄÖÜäöü]{3}", t)]


def _office_xml(content: bytes) -> list[str]:
    """OpenDocument (content.xml) and PowerPoint (ppt/slides): the text of every paragraph and table cell."""
    out = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for member in sorted(z.namelist()):
            if any(member.startswith(p) for p in OFFICE_XML) and member.endswith(".xml"):
                xml = z.read(member).decode("utf-8", "ignore")
                xml = re.sub(r"</(?:text:p|text:h|a:p|w:p)>|<table:table-row[^>]*>", "\n", xml)
                xml = re.sub(r"</table:table-cell>", " | ", xml)
                out += [html.unescape(re.sub(r"<[^>]+>", "", line)).strip(" |") for line in xml.split("\n")]
    return [line for line in out if line.strip()]


def _rtf(text: str) -> list[str]:
    text = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("latin-1"), text)
    text = re.sub(r"\\(?:par|line|row|cell)\b ?", "\n", text)
    text = re.sub(r"\{\\\*[^{}]*\}|\\[a-z]+-?\d* ?|[{}]", "", text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _markup(text: str) -> list[str]:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"(?i)</(?:p|div|tr|li|h\d|table)>|<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", " | ", text)
    return [html.unescape(re.sub(r"<[^>]+>", " ", line)).strip(" |\t") for line in text.splitlines()
            if re.sub(r"<[^>]+>", "", line).strip()]


def _json(content: bytes) -> list[str]:
    try:
        return json.dumps(json.loads(content), indent=1, ensure_ascii=False).splitlines()
    except ValueError:
        return content.decode("utf-8", "replace").splitlines()


def _eml(content: bytes, read, depth: int) -> list[str]:
    """A forwarded mail: its headers that matter, its text, and the text of its attachments."""
    message = email.message_from_bytes(content, policy=policy.default)
    out = [f"{h}: {message[h]}" for h in ("From", "Subject", "Date") if message[h]]
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if filename and read and depth < 2:
            out += [f"[{filename}]", *(_safe(read, filename, data, depth + 1))]
        elif part.get_content_type() == "text/plain":
            out += data.decode(part.get_content_charset() or "utf-8", "replace").splitlines()
        elif part.get_content_type() == "text/html":
            out += _markup(data.decode(part.get_content_charset() or "utf-8", "replace"))
    return out


def _zip(content: bytes, read, depth: int) -> list[str]:
    out = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        files = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith(("__MACOSX/", "."))]
        if sum(i.file_size for i in files) > MAX_ZIP_BYTES or depth >= 2:
            return []
        for info in files[:MAX_ZIP_FILES]:
            if read:
                out += [f"[{info.filename}]", *_safe(read, info.filename, z.read(info), depth + 1)]
    return out


def _safe(read, filename: str, data: bytes, depth: int) -> list[str]:
    try:
        return read(filename, data, depth) or []
    except Exception:  # one unreadable file inside never loses the others
        return []
