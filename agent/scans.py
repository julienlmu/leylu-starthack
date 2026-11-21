"""Scanned attachments (jpg/png, or a PDF without a text layer) read into text, so DG, totals and constraints see them.

5U moves a trap one format further each time (round 10: DG in an xlsx, round 11: in a PDF) and the start kit already
has a scanned JPG tariff, so a scanned packing list or SLI is the likely next step. Only an attachment the backend
can't read costs a call: one transcription through the gateway, no retry, short timeout. The model only copies the
text; every number in it still goes through the same code checks as a typed packing list.
"""
import base64
import os

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
MAX_PDF_PAGES = 3  # a scanned PDF longer than this is not read (cost and time); images are one page
MAX_CHARS = 20000  # the same cap as the backend's attachment text
IMAGES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}

SYSTEM = ("Transcribe every word and number in this document exactly as written, in reading order. "
          "Tables: one row per line, cells separated by ' | ', the header row first. "
          "Do not translate, convert, sum, correct or add anything. If nothing is readable, return an empty text.")
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text"],
          "properties": {"text": {"type": "string"}}}


def readable(filename: str) -> bool:
    """A file type the model can read: an image or a PDF."""
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    return ext in IMAGES or ext == "pdf"


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


def read(filename: str, data: bytes, timeout: float = TIMEOUT_S) -> tuple[str, float]:
    """(text, cost in USD) of a scanned attachment. Raises on any failure: the caller keeps quoting without it."""
    if not readable(filename):
        raise ValueError(f"{filename}: not an image or a PDF")
    if len(data) > MAX_BYTES:
        raise ValueError(f"{filename}: {len(data)} bytes, too big to read")
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf" and pdf_pages(data) > MAX_PDF_PAGES:
        raise ValueError(f"{filename}: {pdf_pages(data)} pages, more than {MAX_PDF_PAGES}")
    b64 = base64.b64encode(data).decode()
    if ext == "pdf":
        part = {"type": "file", "file": {"filename": filename, "file_data": f"data:application/pdf;base64,{b64}"}}
    else:
        part = {"type": "image_url", "image_url": {"url": f"data:{IMAGES[ext]};base64,{b64}", "detail": "high"}}
    data_out, cost = llm.chat_json("scan", SYSTEM, [part], SCHEMA, model=MODEL, timeout=timeout, max_tokens=MAX_TOKENS)
    return (data_out.get("text") or "").strip()[:MAX_CHARS], cost
