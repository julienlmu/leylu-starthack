"""Cloud links: the RFQ (or its packing list) shared as a Dropbox / Google Drive / Docs / Sheets / OneDrive / SharePoint /
Box / WeTransfer link instead of an attachment. Rules, no LLM.

CLOUD_LINKS (default on, off = links are ignored as before):
- find(): https links on the allowlisted hosts only, at most 3 per mail.
- direct(): the direct-download form (Dropbox dl=1, Drive uc?export=download&id=, Docs/Slides export PDF, Sheets export
  CSV, OneDrive/SharePoint download=1).
- fetch(): HTTPS only, every redirect must stay on the allowlist, 10 s in all, 10 MB cap, no cookies or credentials
  sent. An HTML answer is a login, preview or consent page: that is a failure, never read as the request.
The bytes then go through the same attachment reader as a mailed file (pdf/xlsx/csv/docx/zip/audio), so the gate's
injection guard and DG checks see them too. A link that fails leaves the request unread: the RFQ agent asks the
customer for the details in writing (DETAILS_ASK), it never guesses.
"""

import os
import re
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

CLOUD_LINKS = os.environ.get("CLOUD_LINKS", "on").lower() != "off"
TIMEOUT_S = float(os.environ.get("CLOUD_LINK_TIMEOUT_S", "10"))
MAX_BYTES = 10 * 1024 * 1024
MAX_LINKS = 3
MAX_REDIRECTS = 5

# host suffixes we fetch from (a link and every redirect it takes)
HOSTS = ("dropbox.com", "dropboxusercontent.com", "drive.google.com", "docs.google.com", "drive.usercontent.google.com",
         "googleusercontent.com", "onedrive.live.com", "1drv.ms", "sharepoint.com", "files.1drv.com", "box.com",
         "boxcloud.com", "wetransfer.com", "we.tl")
# what a customer writes: we look for links on these hosts only
URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
TYPES = {"application/pdf": ".pdf", "text/csv": ".csv", "text/plain": ".txt", "application/zip": ".zip",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
         "application/vnd.ms-excel": ".xls", "image/png": ".png", "image/jpeg": ".jpg", "audio/mpeg": ".mp3",
         "audio/mp4": ".m4a", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/ogg": ".ogg"}


class LinkError(Exception):
    """The link needs a login, is no file, too big, too slow or leaves the allowlist."""


def allowed(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and not parsed.username and not parsed.password and \
        any(host == h or host.endswith("." + h) for h in HOSTS)


def find(text: str) -> list[str]:
    """Allowlisted https links in the mail, in order, without duplicates."""
    if not CLOUD_LINKS:
        return []
    out = []
    for raw in URL.findall(text or ""):
        url = raw.rstrip(".,;:!?")
        if allowed(url) and url not in out:
            out.append(url)
    return out[:MAX_LINKS]


def _with_query(parsed, **params) -> str:
    query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    query.update(params)
    return urlunparse(parsed._replace(query=urlencode(query)))


def direct(url: str) -> str:
    """The direct-download form of a share link (unchanged when there is none)."""
    parsed = urlparse(url)
    host, path = (parsed.hostname or "").lower(), parsed.path
    if host.endswith("dropbox.com"):
        return _with_query(parsed, dl="1")
    if host == "docs.google.com" and (m := re.match(r"/(document|spreadsheets|presentation)/d/([\w-]+)", path)):
        kind, doc_id = m.groups()
        fmt = "csv" if kind == "spreadsheets" else "pdf"
        gid = parse_qs(parsed.query).get("gid") or re.findall(r"gid=(\d+)", parsed.fragment)
        extra = f"&gid={gid[0]}" if kind == "spreadsheets" and gid else ""
        return f"https://docs.google.com/{kind}/d/{doc_id}/export?format={fmt}{extra}"
    if host == "drive.google.com":
        m = re.match(r"/file/d/([\w-]+)", path)
        file_id = m.group(1) if m else (parse_qs(parsed.query).get("id") or [None])[0]
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    if host.endswith("sharepoint.com") or host in ("onedrive.live.com", "1drv.ms"):
        return _with_query(parsed, download="1")
    return url


def _filename(response: httpx.Response, url: str) -> str:
    disposition = response.headers.get("content-disposition") or ""
    if m := re.search(r"filename\*=(?:UTF-8'')?([^;]+)|filename=\"?([^\";]+)", disposition, re.I):
        name = (m.group(1) or m.group(2)).strip().strip('"')
        if name:
            return os.path.basename(name)
    base = os.path.basename(urlparse(url).path)
    if "." in base:
        return base
    kind = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    return "shared-file" + TYPES.get(kind, ".bin")


def fetch(url: str, transport: httpx.BaseTransport | None = None) -> tuple[str, bytes]:
    """(filename, bytes) of the shared file. Raises LinkError for anything we must not read."""
    deadline = time.monotonic() + TIMEOUT_S
    target = direct(url)
    with httpx.Client(follow_redirects=False, timeout=TIMEOUT_S, transport=transport,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; air-freight-desk)"}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            if not allowed(target):
                raise LinkError(f"not an allowed https file host: {urlparse(target).hostname}")
            if (left := deadline - time.monotonic()) <= 0:
                raise LinkError("too slow")
            client.cookies.clear()  # never carry a session cookie from one hop to the next
            with client.stream("GET", target, timeout=left) as response:
                if response.is_redirect:
                    target = str(response.url.join(response.headers.get("location") or ""))
                    continue
                if response.status_code in (401, 403):
                    raise LinkError("needs a login")
                if response.status_code != 200:
                    raise LinkError(f"HTTP {response.status_code}")
                kind = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
                if kind in ("text/html", "application/xhtml+xml"):
                    raise LinkError("a web page (login, preview or consent), not a file")
                if int(response.headers.get("content-length") or 0) > MAX_BYTES:
                    raise LinkError("larger than 10 MB")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        raise LinkError("larger than 10 MB")
                    if time.monotonic() > deadline:
                        raise LinkError("too slow")
                return _filename(response, target), bytes(data)
    raise LinkError("too many redirects")


# "please upload the quote to our Dropbox / Drive / SharePoint folder": we can't (no credentials, nothing outside the
# mailbox): the quote goes in the mail body and as the PDF, with one sentence saying so.
UPLOAD_ASK = re.compile(
    r"\b(?:upload|put|save|drop|place|add|store|share|lade\w*|hochlad\w*|speicher\w*|ablegen|leg\w*)\b[^.!?\n]{0,60}?"
    r"\b(?:to|in|into|on|onto|in\s+den|in\s+die|in\s+unser\w*|auf)\b[^.!?\n]{0,25}?"
    r"\b(?:drive|dropbox|onedrive|sharepoint|box\s+folder|shared\s+folder|folder|ordner|teams)\b", re.I)


def asks_upload(text: str) -> bool:
    return CLOUD_LINKS and bool(UPLOAD_ASK.search(text or ""))


UPLOAD_NOTE = ("I can't upload files to external folders, so the quote is written above and attached to this mail as a "
               "PDF.")
