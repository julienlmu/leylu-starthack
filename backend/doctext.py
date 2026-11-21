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
from email import policy

MAX_ZIP_FILES, MAX_ZIP_BYTES = 20, 20_000_000  # a zip bomb never gets unpacked
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
        return _zip(content, read, depth)
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
            files = [m for m in t.getmembers() if m.isfile()]
            if sum(m.size for m in files) > MAX_ZIP_BYTES or depth >= 2:
                return []
            for member in files[:MAX_ZIP_FILES]:
                if read and (f := t.extractfile(member)):
                    out += [f"[{member.name}]", *_safe(read, member.name, f.read(), depth + 1)]
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
