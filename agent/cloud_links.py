"""Cloud share links next to links.py (which downloads and reads every RFQ link safely). Rules only, no LLM.

CLOUD_LINKS (default on, off = as before):
- find(): links on file-share hosts (Dropbox, Google Drive/Docs/Sheets, OneDrive/SharePoint, Box, WeTransfer). When the
  request sits only behind such a link and nothing could be read (a login, a JavaScript viewer like WeTransfer), the
  RFQ agent asks for the details in writing in the first minute ("I can't open the link you shared ...") instead of
  handing the round to a person; it never guesses.
- asks_upload(): "please upload the quote to our Dropbox / Drive / SharePoint folder": we can't (no credentials, nothing
  outside the mailbox), so the quote goes in the mail body and as the offer file, with one sentence saying so.
"""

import os
import re
from urllib.parse import urlparse

CLOUD_LINKS = os.environ.get("CLOUD_LINKS", "on").lower() != "off"
HOSTS = ("dropbox.com", "dropboxusercontent.com", "drive.google.com", "docs.google.com", "drive.usercontent.google.com",
         "onedrive.live.com", "1drv.ms", "sharepoint.com", "box.com", "wetransfer.com", "we.tl")
URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


def share_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in HOSTS)


def find(text: str) -> list[str]:
    """File-share links in the mail, in order, without duplicates."""
    if not CLOUD_LINKS:
        return []
    out = []
    for raw in URL.findall(text or ""):
        url = raw.rstrip(".,;:!?")
        if share_host(url) and url not in out:
            out.append(url)
    return out[:3]


UPLOAD_ASK = re.compile(
    r"\b(?:upload|put|save|drop|place|add|store|share|lade\w*|hochlad\w*|speicher\w*|ablegen|leg\w*)\b[^.!?\n]{0,60}?"
    r"\b(?:to|in|into|on|onto|in\s+den|in\s+die|in\s+unser\w*|auf)\b[^.!?\n]{0,25}?"
    r"\b(?:drive|dropbox|onedrive|sharepoint|box\s+folder|shared\s+folder|folder|ordner|teams)\b", re.I)


def asks_upload(text: str) -> bool:
    return CLOUD_LINKS and bool(UPLOAD_ASK.search(text or ""))


UPLOAD_NOTE = ("I can't upload files to external folders, so the quote is written above and attached to this mail as a "
               "file.")
