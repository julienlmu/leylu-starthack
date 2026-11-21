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
# gpt-4.1-mini reads images and is priced in llm.PRICES; IMAGE_MODEL=gpt-6-luna once a test call shows it takes images
MODEL = os.environ.get("IMAGE_MODEL") or "gpt-4.1-mini"
TIMEOUT_S = float(os.environ.get("IMAGE_READ_TIMEOUT", "15"))  # the bid round waits 90 s anyway; never longer
MAX_BYTES = 8_000_000
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


def read(filename: str, data: bytes) -> tuple[str, float]:
    """(text, cost in USD) of a scanned attachment. Raises on any failure: the caller keeps quoting without it."""
    if not readable(filename):
        raise ValueError(f"{filename}: not an image or a PDF")
    if len(data) > MAX_BYTES:
        raise ValueError(f"{filename}: {len(data)} bytes, too big to read")
    b64 = base64.b64encode(data).decode()
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        part = {"type": "file", "file": {"filename": filename, "file_data": f"data:application/pdf;base64,{b64}"}}
    else:
        part = {"type": "image_url", "image_url": {"url": f"data:{IMAGES[ext]};base64,{b64}", "detail": "high"}}
    data_out, cost = llm.chat_json("scan", SYSTEM, [part], SCHEMA, model=MODEL, timeout=TIMEOUT_S)
    return (data_out.get("text") or "").strip()[:MAX_CHARS], cost
