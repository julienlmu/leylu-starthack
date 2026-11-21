"""Scanned attachments read into text, so DG, totals and constraints see them: an image, a PDF without a text layer,
a scanned page inside a PDF whose other pages have text, and pictures pasted into a Word/Excel/PowerPoint file.

5U moves a trap one format further each time (round 10: DG in an xlsx, round 11: in a PDF) and the start kit already
has a scanned JPG tariff, so a scanned packing list or SLI is the likely next step. Only an attachment the backend
can't read costs a call: one transcription through the gateway, no retry, short timeout. The model only copies the
text; every number in it still goes through the same code checks as a typed packing list.
"""
import base64
import io
import os
import re
import struct
import zipfile

import llm

IMAGE_READ = os.environ.get("IMAGE_READ", "on").lower() != "off"
# gpt-6-luna takes images and PDF file parts through the gateway (live tests Sat 21:05 and 21:18: the Danube Wings JPG
# and the same page as an image-only PDF, 63 of 63 rates and minimums right each time, $0.00055 / $0.00035); reasoning
# stays off via llm.OPTIONS. IMAGE_MODEL=gpt-4.1-mini is the priced fallback.
MODEL = os.environ.get("IMAGE_MODEL") or "gpt-6-luna"
TIMEOUT_S = float(os.environ.get("IMAGE_READ_TIMEOUT", "15"))  # one scan; never longer
BUDGET_S = float(os.environ.get("IMAGE_READ_BUDGET", "30"))  # all scans of one RFQ: the bid requests wait for them
MAX_BYTES = 8_000_000
MAX_TOKENS = 2000  # a packing list or a tariff page is ~400 tokens of text; caps the cost of a long scan
# A PDF up to this many pages goes to the model whole, so every page counts (a typed page 1 with CCITT / JBIG2 / Flate
# scans behind it: no JPEG we could cut out); ~1.5k input tokens a page, $0.0015 for 10 on luna. A longer one: only the
# JPEG images of its first MAX_PICTURES large pages; the agent notes the pages it didn't read.
MAX_PDF_PAGES = 10
# A picture inside a typed file costs a vision call only from ~500 x 500 px: a scanned page is 1240 x 1754, a pasted
# packing-list screenshot ~900 x 400; letterhead logos (300 x 100) and signatures (200 x 60) never pay (review of #175)
MIN_PIXELS = 250_000
# A dangerous goods sticker is a diamond in a square picture and can be small (150 x 150): square-ish pictures from
# 80 x 80 px are read too (icons are 16-64), wide ones (letterhead 300 x 100, signature 200 x 60) are not. A square logo costs one call.
LABEL_SIDE, LABEL_RATIO = 80, 1.5
MAX_PICTURES = 3  # pictures sent in one call (pictures inside a Word/Excel/PowerPoint file, pages of a long scan)
OFFICE = {"docx", "docm", "xlsx", "xlsm", "pptx", "pptm", "odt", "ods", "odp"}
MEDIA_DIRS = ("word/media/", "xl/media/", "ppt/media/", "Pictures/")  # where these zips keep their pictures
MAX_CHARS = 20000  # the same cap as the backend's attachment text
IMAGES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}

SYSTEM = ("Transcribe every word and number in this document exactly as written, in reading order. "
          "Tables: one row per line, cells separated by ' | ', the header row first. "
          "Do not translate, convert, sum, correct or add anything. Several pictures: transcribe each one in order, "
          "separated by a blank line. "
          # a hazard sticker carries almost no text (a "9" in a diamond): say what it is, so the DG check sees it
          "For every dangerous goods hazard label, mark or pictogram you see (a diamond label, the lithium battery "
          "mark, a flame, skull, corrosive or radioactive symbol, a cargo-aircraft-only label) add a line "
          "'Dangerous goods label: Class <n> (<name>)', e.g. 'Dangerous goods label: Class 9 (lithium batteries)'. "
          "If nothing is readable, return an empty text.")
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text"],
          "properties": {"text": {"type": "string"}}}


def _ext(filename: str) -> str:
    return (filename or "").lower().rsplit(".", 1)[-1]


def readable(filename: str) -> bool:
    """A file type the model can read: an image or a PDF."""
    return _ext(filename) in IMAGES or _ext(filename) == "pdf"


def needs_scan(filename: str, data: bytes, text: str | None) -> bool:
    """True when part of the attachment is only a picture: the whole file (no text from the backend), a scanned page
    in a PDF whose other pages have text, or a packing list pasted as a picture into a Word/Excel/PowerPoint file.
    5U hides the DG line one step further each time; the text reader can't see any of these."""
    ext, empty = _ext(filename), not (text or "").strip()
    try:
        if ext in IMAGES:
            return empty
        if ext == "pdf":
            return empty or bool(scanned_pages(data))
        if ext in OFFICE:
            return bool(office_pictures(data))
        if ext == "zip":
            return bool(archive_pictures(data))
    except Exception:  # a broken file is the text reader's problem, never a crash here
        return False
    return False


def _dims(data: bytes) -> tuple[int, int] | None:
    """(width, height) of a PNG, GIF or JPEG from its header; None when unknown."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):  # start of frame: height, width
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return width, height
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    return None


def _worth_reading(width: int, height: int) -> bool:
    """A picture inside a typed file that may hold what the text lacks: big (a page, a screenshot), or square-ish
    (a dangerous goods sticker)."""
    if width * height >= MIN_PIXELS:
        return True
    return min(width, height) >= LABEL_SIDE and max(width, height) <= LABEL_RATIO * min(width, height)


def _area(data: bytes) -> int:
    dims = _dims(data)
    return dims[0] * dims[1] if dims else (MIN_PIXELS if len(data) >= 5_000 else 0)  # unknown size: by bytes


def archive_pictures(data: bytes) -> list[tuple[str, bytes]]:
    """Pictures inside a zip (a photographed packing list, a DG sticker), read in memory, never extracted; encrypted,
    oversized and icon-sized ones left out; at most MAX_PICTURES."""
    found = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist()[:50]:
            if _ext(info.filename) in IMAGES and not info.flag_bits & 1 and info.file_size <= MAX_BYTES:
                with z.open(info) as f:
                    picture = f.read(MAX_BYTES + 1)
                dims = _dims(picture)
                if len(picture) <= MAX_BYTES and (_worth_reading(*dims) if dims else len(picture) >= 5_000):
                    found.append((info.filename, picture))
    return sorted(found, key=lambda f: -_area(f[1]))[:MAX_PICTURES]


def office_pictures(data: bytes) -> list[tuple[str, bytes]]:
    """The largest pictures inside a docx/xlsx/pptx/OpenDocument file (word/media/..., xl/media/...), logos left out."""
    found = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.filename.startswith(MEDIA_DIRS) and _ext(info.filename) in IMAGES and info.file_size <= MAX_BYTES:
                picture = z.read(info.filename)
                dims = _dims(picture)
                if _worth_reading(*dims) if dims else len(picture) >= 5_000:
                    found.append((info.filename, picture))
    return sorted(found, key=lambda f: -_area(f[1]))[:MAX_PICTURES]


IMAGE_OBJECT = re.compile(rb"/Subtype\s*/Image\b")


def scanned_pages(data: bytes) -> list[bytes | None]:
    """The large images in a PDF (a scanned page, not a logo), found in the raw bytes, no parser. An image is a stream,
    so its dictionary is never inside a compressed object stream. Each entry is the JPEG itself when the image is
    stored as one (DCTDecode, what scanners write), else None."""
    pages = []
    for match in IMAGE_OBJECT.finditer(data):
        start, end = data.rfind(b"obj", 0, match.start()), data.find(b"stream", match.end())
        if start < 0 or end < 0 or end - start > 4000:
            continue
        head = data[start:end]
        width, height = re.search(rb"/Width\s+(\d+)", head), re.search(rb"/Height\s+(\d+)", head)
        if not width or not height or not _worth_reading(int(width[1]), int(height[1])):
            continue
        jpeg = None
        if b"DCTDecode" in head:
            body_start = end + len(b"stream")
            body_start += 2 if data[body_start:body_start + 2] == b"\r\n" else 1
            body = data[body_start:data.find(b"endstream", body_start)].rstrip(b"\r\n")
            jpeg = body if body[:2] == b"\xff\xd8" else None
        pages.append(jpeg)
    return pages


_done: dict[str, str] = {}  # attachment key → its text: a resumed RFQ (pickup answer) never pays for the same scan twice


def pdf_pages(data: bytes) -> int:
    """Page objects in a PDF (counted in the raw bytes, no parser): enough to refuse a long scanned document."""
    return data.count(b"/Type /Page") + data.count(b"/Type/Page") - data.count(b"/Type /Pages") - data.count(b"/Type/Pages")


def read_once(key: str, filename: str, data: bytes, timeout: float = TIMEOUT_S) -> tuple[str, float]:
    """read(), remembered by `key` (mail id + attachment): the second time it costs nothing."""
    if key in _done:
        return _done[key], 0.0
    try:
        text, cost = read(filename, data, timeout)
    except Exception:
        _done[key] = ""  # a failed read (timeout, refusal) is not paid for a second time either
        raise
    _done[key] = text
    return text, cost


def _image(ext: str, data: bytes) -> dict:
    url = f"data:{IMAGES[ext]};base64,{base64.b64encode(data).decode()}"
    return {"type": "image_url", "image_url": {"url": url, "detail": "high"}}


def read(filename: str, data: bytes, timeout: float = TIMEOUT_S) -> tuple[str, float]:
    """(text, cost in USD) of the picture parts of an attachment: an image, a scanned PDF (the whole file up to
    MAX_PDF_PAGES pages, else the JPEGs of its first 3 large pages), or the pictures inside an Office file. One call.
    Raises on any failure: the caller keeps quoting without it."""
    ext = _ext(filename)
    if len(data) > MAX_BYTES:
        raise ValueError(f"{filename}: {len(data)} bytes, too big to read")
    if ext in IMAGES:
        parts = [_image(ext, data)]
    elif ext == "pdf" and pdf_pages(data) <= MAX_PDF_PAGES:
        b64 = base64.b64encode(data).decode()
        parts = [{"type": "file", "file": {"filename": filename, "file_data": f"data:application/pdf;base64,{b64}"}}]
    elif ext == "pdf":
        jpegs = [jpeg for jpeg in scanned_pages(data) if jpeg][:MAX_PICTURES]
        if not jpegs:
            raise ValueError(f"{filename}: {pdf_pages(data)} pages, more than {MAX_PDF_PAGES}, no JPEG page to read")
        parts = [_image("jpg", jpeg) for jpeg in jpegs]
    elif ext in OFFICE or ext == "zip":
        pictures = office_pictures(data) if ext in OFFICE else archive_pictures(data)
        parts = [_image(_ext(name), picture) for name, picture in pictures]
        if not parts:
            raise ValueError(f"{filename}: no picture to read")
    else:
        raise ValueError(f"{filename}: not an image, a PDF or an Office file")
    data_out, cost = llm.chat_json("scan", SYSTEM, parts, SCHEMA, model=MODEL, timeout=timeout, max_tokens=MAX_TOKENS)
    return (data_out.get("text") or "").strip()[:MAX_CHARS], cost
