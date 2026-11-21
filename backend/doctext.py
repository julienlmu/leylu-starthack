"""Text from the document types ingest.extract_lines doesn't read itself: old Office (.doc, .xls, .msg), OpenDocument
(.odt, .ods, .odp), .pptx, .rtf, .html, .xml, .json, .tsv, .eml (with its attachments) and .zip (each file inside).
Standard library only, no LLM: the agent's DG, packing-list and constraint checks then read these like a PDF.
A file with no or a wrong extension is recognised by its first bytes.
"""

import bz2
import email
import gzip
import html
import io
import json
import lzma
import os
import re
import sqlite3
import tarfile
import tempfile
import tomllib
import zipfile
import zlib
from email import policy

MAX_ZIP_FILES, MAX_ZIP_BYTES = 50, 20_000_000  # a zip bomb never gets unpacked (bytes counted as they are read)
# Inside an archive only documents are read (in memory, never extracted to disk, never executed): a zipped packing list
# is a likely 5U trap. Executables, scripts, macro files and archives inside an archive are never opened (depth 1);
# pictures are left to the agent's scan reader.
ARCHIVE_MEMBERS = {"xlsx", "xls", "csv", "pdf", "docx", "txt"}
MAX_RAW_BYTES = 5_000_000  # the raw-strings fallback looks at the first 5 MB only
MAX_ROWS = 500  # per database table / dBase file
# Plain text in all but name: the content is read as it is.
TEXT = {"md", "markdown", "log", "text", "yaml", "yml", "rdf", "ttl", "nt", "n3", "sql", "hl7", "dxf", "step", "stp",
        "iges", "igs", "gbr", "ger", "gerber", "gtl", "gbl", "gto", "gbo", "gts", "gbs", "drl", "sp", "spice", "cir",
        "net", "v", "sv", "vhd", "vhdl", "ini", "cfg", "conf", "properties", "eps", "ps", "tex", "srt", "vtt"}
MARKUP = {"html", "htm", "xhtml", "xml", "svg", "gml", "kml", "rdfxml", "owl", "xsd", "xlf"}
JSONS = {"json", "geojson", "jsonl", "ndjson", "topojson"}
ZIPS = {"zip", "epub", "jar", "apk", "aab", "appx", "msix", "xpi", "kmz", "odg", "docm", "xlsm", "pptm", "nupkg"}
TARS = {"tar", "tgz", "tbz", "tbz2", "txz"}
SQLITE = {"sqlite", "sqlite3", "db", "db3", "gpkg", "mbtiles"}
# Read by the agent's scan / transcription reader (scans.py, media.py), never by raw strings: junk text from an image
# or a recording would make the agent think the attachment was read and skip the real reader.
MEDIA = {"jpg", "jpeg", "png", "gif", "webp", "tif", "tiff", "bmp", "heic", "heif", "wav", "bwf", "flac", "mp3", "aac",
         "m4a", "ogg", "oga", "opus", "aif", "aiff", "amr", "mid", "midi", "mp4", "m4v", "mkv", "mov", "avi", "webm",
         "wmv", "3gp", "mpeg", "mpg", "mxf", "dpx", "ffv1", "nut"}
OFFICE_XML = {"word/document.xml", "word/header", "word/footer", "ppt/slides/slide", "ppt/notesSlides/",
              "ppt/comments/", "xl/sharedStrings.xml", "xl/worksheets/sheet", "content.xml"}


def lines(filename: str, content: bytes, read=None, depth: int = 0, passwords=()) -> list[str] | None:
    """The file as text lines, or None for a type this module doesn't know. `read(name, bytes)` reads a file found
    inside a zip or an e-mail (ingest.extract_lines, so a PDF inside a zip is read too). `passwords`: the ones the
    mail body names, tried on an encrypted zip."""
    name = filename.lower()
    kind = name.rsplit(".", 1)[-1] if "." in name else _sniff(content)
    if kind in ("doc", "xls", "msg", "ole"):
        return _ole_strings(content)
    if kind in ("odt", "ods", "odp", "pptx", "zip-office"):
        return _office_xml(content)
    if kind == "rtf":
        return _rtf(content.decode("latin-1", "replace"))
    if kind in MARKUP:
        return _markup(content.decode("utf-8", "replace"))
    if kind in JSONS:
        return _json(content) if kind not in ("jsonl", "ndjson") else content.decode("utf-8", "replace").splitlines()
    if kind == "toml":
        return _toml(content)
    if kind in SQLITE or content[:16] == b"SQLite format 3\x00":
        return _sqlite(content)
    if kind == "dbf":
        return _dbf(content)
    if kind == "ai" and content[:4] == b"%PDF" and read:  # Illustrator files are PDFs inside
        return read(filename + ".pdf", content, depth)
    if kind in TARS or name.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        return _tar(content, read, depth)
    if kind in ("gz", "bz2", "xz", "lzma"):
        return _single(name, content, read, depth)
    if kind == "deb":
        return _deb(content, read, depth)
    if kind == "stl" and not content[:5].lower() == b"solid":
        return _strings(content[:80])  # binary STL: only the header carries text
    if kind in ("tsv", "tab"):
        return [" | ".join(row.split("\t")) for row in content.decode("utf-8", "replace").splitlines()]
    if kind == "eml":
        return _eml(content, read, depth)
    if kind in ZIPS:
        return _zip(content, read, depth, passwords)
    if (kind in TEXT or kind == "stl") and b"\x00" not in content[:4096]:
        return content.decode("utf-8", "replace").splitlines()  # (a binary .vhd is a disk image, not VHDL: strings)
    if kind in MEDIA:
        return None  # scans.py / media.py read these
    if kind == "csv" or kind == "pdf" or kind == "docx" or kind == "xlsx" or kind == "txt":
        return None  # ingest.extract_lines reads these itself
    # Everything else (Parquet, ORC, HDF5, Avro, Protobuf, Thrift, MessagePack, Access, SQL Server, DWG, RVT, F3D,
    # GDSII, PSD, XCF, 7z, RAR, ISO, IMG, VHD, WIM, DMG, MSI, RPM, …): the readable strings in its bytes. Enough for a UN
    # number, a weight or a name; decoding them fully would need packages (pyarrow, h5py, …).
    return _strings(content[:MAX_RAW_BYTES]) or None


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


def _strings(content: bytes) -> list[str]:
    """Readable runs in any binary file (UTF-8/latin-1 and UTF-16), like the Unix `strings`, without noise."""
    found = [c.decode("utf-16-le", "ignore") for c in re.findall(rb"(?:[\x20-\x7e]\x00){6,}", content)]
    found += [c.decode("utf-8", "ignore") for c in re.findall(rb"[\x20-\x7e\xc2-\xf4\x80-\xbf]{6,}", content)]
    return [t.strip() for t in dict.fromkeys(found) if len(re.findall(r"[A-Za-z]", t)) >= 4][:5000]


def _toml(content: bytes) -> list[str]:
    try:
        return json.dumps(tomllib.loads(content.decode("utf-8", "replace")), indent=1, default=str,
                          ensure_ascii=False).splitlines()
    except tomllib.TOMLDecodeError:
        return content.decode("utf-8", "replace").splitlines()


def _sqlite(content: bytes) -> list[str]:
    """Every table of an SQLite / GeoPackage file, MAX_ROWS rows each, read-only from a temporary copy."""
    out = []
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        f.write(content)
    try:
        db = sqlite3.connect(f"file:{f.name}?mode=ro", uri=True)
        try:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables[:50]:
                rows = db.execute(f'SELECT * FROM "{table.replace(chr(34), "")}" LIMIT {MAX_ROWS}')
                header = [d[0] for d in rows.description]
                out += [f"[{table}]", " | ".join(header)]
                out += [" | ".join("" if v is None else (v if isinstance(v, str) else repr(v) if isinstance(v, bytes)
                                                         else str(v)) for v in row) for row in rows]
        finally:
            db.close()
    except sqlite3.DatabaseError:
        return _strings(content[:MAX_RAW_BYTES])
    finally:
        os.unlink(f.name)
    return out


def _dbf(content: bytes) -> list[str]:
    """A dBase table (also a Shapefile's .dbf attributes): header row, then MAX_ROWS records, cells " | "."""
    try:
        records, header_len, record_len = int.from_bytes(content[4:8], "little"), \
            int.from_bytes(content[8:10], "little"), int.from_bytes(content[10:12], "little")
        fields, pos = [], 32
        while pos + 32 <= header_len and content[pos] != 0x0D:
            fields.append((content[pos:pos + 11].split(b"\x00")[0].decode("latin-1"), content[pos + 16]))
            pos += 32
        out = [" | ".join(f for f, _ in fields)]
        for i in range(min(records, MAX_ROWS)):
            start = header_len + i * record_len + 1  # the first byte flags a deleted record
            row, offset = [], 0
            for _, size in fields:
                row.append(content[start + offset:start + offset + size].decode("latin-1").strip())
                offset += size
            out.append(" | ".join(row))
        return out
    except (IndexError, ValueError):
        return _strings(content[:MAX_RAW_BYTES])


def _tar(content: bytes, read, depth: int) -> list[str]:
    out = []
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as t:
            files = [m for m in t.getmembers() if m.isfile() and _member_ok(m.name)]
            if depth >= 1:
                return []
            budget = MAX_ZIP_BYTES
            for member in files[:MAX_ZIP_FILES]:
                if read and (f := t.extractfile(member)):
                    data = f.read(budget + 1)
                    budget -= len(data)
                    if budget < 0:
                        return []  # more than 20 MB unpacked: a bomb, nothing is read
                    out += [f"[{member.name}]", *_safe(read, member.name, data, depth + 1)]
    except tarfile.TarError:
        return []
    return out


def _single(name: str, content: bytes, read, depth: int) -> list[str]:
    """report.csv.gz → the text of report.csv (one compressed file, capped)."""
    ext = name.rsplit(".", 1)[-1]
    try:
        with {"gz": gzip.open, "bz2": bz2.open}.get(ext, lzma.open)(io.BytesIO(content)) as f:
            data = f.read(MAX_ZIP_BYTES + 1)
    except (OSError, EOFError, lzma.LZMAError):
        return []
    if len(data) > MAX_ZIP_BYTES or depth >= 2 or not read:
        return []
    inner = name[: -len(ext) - 1] or "file"
    return _safe(read, inner, data, depth + 1)


def _deb(content: bytes, read, depth: int) -> list[str]:
    """A Debian package (an `ar` archive): the files of its data.tar.*."""
    out, pos = [], 8
    while content[:8] == b"!<arch>\n" and pos + 60 <= len(content):
        member, size = content[pos:pos + 16].decode("latin-1").strip().rstrip("/"), int(content[pos + 48:pos + 58])
        if member.startswith(("data.tar", "control.tar")):
            out += _tar(content[pos + 60:pos + 60 + size], read, depth)
        pos += 60 + size + (size % 2)
    return out


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
                xml = re.sub(r"</(?:text:p|text:h|a:p|w:p|p:cm)>|<table:table-row[^>]*>", "\n", xml)
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


def _xml_text(xml: str) -> list[str]:
    """Every text node of an XML / XHTML snippet (scripts left out), one per line."""
    xml = re.sub(r"(?is)<(script|style)\b.*?</\1>|<!--.*?-->", " ", xml)
    return [t for raw in re.findall(r">([^<]+)<", f">{xml}<") if (t := html.unescape(raw).strip())]


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


def _zip(content: bytes, read, depth: int, passwords=()) -> list[str]:
    out, locked = [], []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        files = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith(("__MACOSX/", "."))
                 and _member_ok(i.filename)]
        if sum(i.file_size for i in files) > MAX_ZIP_BYTES or depth >= 1:
            return []
        budget = MAX_ZIP_BYTES
        for info in files[:MAX_ZIP_FILES]:
            if read:
                if (data := _unzip(z, info, passwords, budget)) is None:
                    locked.append(info.filename)
                    continue
                budget -= len(data)
                if budget < 0:
                    return []  # the sizes the zip states were a lie: more than 20 MB unpacked, nothing is read
                out += [f"[{info.filename}]", *_safe(read, info.filename, data, depth + 1)]
    if locked and not out:
        raise ValueError(f"password-protected zip ({', '.join(locked[:3])}): no password from the mail opens it"
                         + (" (AES-encrypted: not supported)" if any(map(_aes, files)) else ""))
    return out + [f"[{name}: password-protected, not read]" for name in locked]


def _member_ok(name: str) -> bool:
    return name.lower().rsplit(".", 1)[-1] in ARCHIVE_MEMBERS


def _aes(info: zipfile.ZipInfo) -> bool:
    return info.compress_type == 99  # WinZip AES: zipfile only decrypts ZipCrypto


def _unzip(z: zipfile.ZipFile, info: zipfile.ZipInfo, passwords, budget: int = MAX_ZIP_BYTES) -> bytes | None:
    """The file's bytes (at most budget + 1, read in memory); an encrypted one with the first password from the mail
    that opens it, else None."""
    if not info.flag_bits & 1:
        with z.open(info) as f:
            return f.read(budget + 1)
    for password in [] if _aes(info) else passwords:
        try:
            with z.open(info, pwd=password.encode()) as f:
                return f.read(budget + 1)
        except (RuntimeError, zipfile.BadZipFile, zlib.error):  # wrong password (or the 1-in-256 false check byte)
            continue
    return None


def _safe(read, filename: str, data: bytes, depth: int) -> list[str]:
    try:
        return read(filename, data, depth) or []
    except Exception:  # one unreadable file inside never loses the others
        return []


# Parts of a PDF / Word / Excel file that the page-text readers skip, where a DG line can hide.
WORD_PARTS = re.compile(r"word/(?:document|header\d*|footer\d*|comments|footnotes|endnotes)\.xml")
# Charts and SmartArt diagrams keep their labels as DrawingML <a:t> / chart <c:v> text, outside the page text.
WORD_DRAWINGS = re.compile(r"word/(?:charts/chart\d*|diagrams/data\d*)\.xml")
DRAWING_TEXT = re.compile(r"<(a:t|c:v)>([^<]*)</\1>")
WORD = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>|<(/?)w:(p|tc|tr|tbl)\b[^>]*?(/?)>|<w:(?:tab|br|cr)\b[^>]*/>")


def _word(xml: str) -> list[str]:
    """Every <w:t> of a Word XML part in reading order (text boxes, nested tables, tracked inserts included; deleted
    text is <w:delText> and stays out). A table row is one line, cells joined with " | "."""
    xml = re.sub(r"(?s)<mc:Fallback>.*?</mc:Fallback>", "", xml)  # the VML copy of a text box
    text, tables = [], 0
    for m in WORD.finditer(xml):
        if m[1] is not None:
            text.append(html.unescape(m[1]))
        elif m[3] is None:
            text.append(" ")  # tab / line break
        elif m[3] == "tbl":
            tables += -1 if m[2] else 0 if m[4] else 1
        elif m[2] or m[4]:  # </w:p>, </w:tc>, </w:tr> (or an empty <w:p/>)
            text.append({"p": " " if tables else "\n", "tc": " | ", "tr": "\n"}[m[3]])
    return [line for raw in "".join(text).split("\n") if (line := re.sub(r"\s+", " ", raw).strip(" |"))]


def _known(have: list[str]):
    """A test whether a line is already in `have` (whitespace aside, whole line or every cell of it)."""
    seen = {re.sub(r"\s+", "", part) for line in have for part in [line, *line.split("|")]}
    return lambda line: all(re.sub(r"\s+", "", part) in seen for part in line.split("|"))


def word_extra(content: bytes, have: list[str]) -> list[str]:
    """What python-docx's paragraphs and top-level tables miss: headers, footers, text boxes, nested tables, tracked
    inserts, comments, footnotes, endnotes, chart and SmartArt labels. Only lines not in `have` already."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        parts = sorted((n for n in z.namelist() if WORD_PARTS.fullmatch(n)), key=lambda n: (n != "word/document.xml", n))
        found = [line for n in parts for line in _word(z.read(n).decode("utf-8", "ignore"))]
        found += [line for n in sorted(z.namelist()) if WORD_DRAWINGS.fullmatch(n)
                  for _, raw in DRAWING_TEXT.findall(z.read(n).decode("utf-8", "ignore"))
                  if re.search(r"[^\W\d_]", line := html.unescape(raw).strip())]  # labels; plain chart numbers left out
    known = _known(have)
    return [line for line in dict.fromkeys(found) if not known(line)]


def excel_extra(content: bytes) -> list[str]:
    """Cell comments (old and threaded) and the formula of a cell without a cached value (a file a script wrote:
    openpyxl's data_only read gives it as empty), so a string literal in it is seen."""
    out = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for n in sorted(z.namelist()):
            if re.fullmatch(r"xl/(?:comments\d*|comments/[^/]+|threadedComments/[^/]+)\.xml", n):  # Excel, openpyxl
                xml = z.read(n).decode("utf-8", "ignore")
                for ref, body in re.findall(r'<(?:comment|threadedComment)\b[^>]*?\bref="([^"]+)"[^>]*>(.*?)'
                                            r'</(?:comment|threadedComment)>', xml, re.S):
                    out.append(f"comment {ref}: {html.unescape(re.sub(r'<[^>]+>', '', body)).strip()}")
            elif re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n) and b"<f" in (raw := z.read(n)):
                for ref, body in re.findall(r'<c\b[^>/]*?\br="([^"]+)"[^>/]*>(.*?)</c>', raw.decode("utf-8", "ignore"),
                                            re.S):
                    if (f := re.search(r"<f\b[^>]*>([^<]+)</f>", body)) and not re.search(r"<v>[^<]+</v>", body):
                        out.append(f"formula {ref}: ={html.unescape(f[1])}")
    return out


def pdf_extra(pdf, read, depth: int) -> list[str]:
    """Filled form fields ("name: value": a fillable SLI), comment / sticky-note text, and the files embedded in the
    PDF (attachments and file-attachment notes), read through `read` up to 2 levels deep."""
    from pdfminer.pdftypes import resolve1
    from pdfminer.utils import decode_text

    def text(value) -> str:
        value = resolve1(value)
        if isinstance(value, bytes):
            return decode_text(value)
        if isinstance(value, list):
            return ", ".join(text(v) for v in value)
        return str(getattr(value, "name", "" if value is None else value))  # a checkbox's /Yes is a name

    out, files = [], []

    def fields(kids, prefix: str, level: int):
        for field in (resolve1(kids) or [])[:2000] if level < 10 else []:
            if not isinstance(field := resolve1(field), dict):
                continue
            name = ".".join(p for p in (prefix, text(field.get("T"))) if p)
            if (value := text(field.get("V")).strip()) and value != "Off":
                out.append(f"{name}: {value}")
            fields(field.get("Kids"), name, level + 1)

    def tree(node, level: int):  # the /EmbeddedFiles name tree
        node = resolve1(node) or {}
        names = resolve1(node.get("Names")) or []
        files.extend(resolve1(spec) for spec in names[1::2])
        for kid in (resolve1(node.get("Kids")) or []) if level < 10 else []:
            tree(kid, level + 1)

    catalog = pdf.doc.catalog
    acroform = resolve1(catalog.get("AcroForm")) or {}
    fields(acroform.get("Fields"), "", 0)
    xfa = resolve1(acroform.get("XFA"))  # an XFA form keeps its values as XML: one stream, or [name stream ...]
    for packet in (xfa[1::2] if isinstance(xfa, list) else [xfa] if xfa is not None else [])[:20]:
        try:
            out += [f"form: {t}" for t in _xml_text(resolve1(packet).get_data()[:MAX_RAW_BYTES].decode("utf-8", "ignore"))]
        except AttributeError:  # not a stream
            continue
    tree((resolve1(catalog.get("Names")) or {}).get("EmbeddedFiles"), 0)
    for page in pdf.pages:
        for annot in resolve1(page.page_obj.annots) or []:
            if not isinstance(annot := resolve1(annot), dict):
                continue
            for note in (text(annot.get("Contents")), " ".join(_xml_text(text(annot.get("RC"))))):  # plain, rich text
                if note := re.sub(r"\s+", " ", note).strip():
                    out.append(f"comment: {note}")
            if annot.get("FS") is not None:
                files.append(resolve1(annot["FS"]))
    out = list(dict.fromkeys(out))
    for spec in files[:MAX_ZIP_FILES] if read and depth < 2 else []:
        try:
            filename = text(spec.get("UF") or spec.get("F")) or "embedded"
            data = resolve1(resolve1(spec["EF"]).get("F")).get_data()
        except (AttributeError, KeyError, TypeError):
            continue
        if len(data) <= MAX_ZIP_BYTES:
            out += [f"[{filename}]", *_safe(read, filename, data, depth + 1)]
    return out
