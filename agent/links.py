"""Links in an RFQ ("packing list: https://…", a shared Drive/Dropbox file, a web page with the shipment data): read
like an attachment, so totals, DG and constraints see them. Rules only, no LLM, no browser.

Safety (the mail is untrusted, so is every link in it):
- No browser and no JavaScript: one plain HTTP GET per hop, so there are no popups, dialogs, cookie walls or
  downloads that run. Scripts, styles, iframes and popup/cookie/newsletter overlays are cut out of a page before its
  text is read. A login page (password field) is never used: we never type anything into a site.
- Only http/https on the default port; no user:password@ in the URL; no IP-literal or punycode (look-alike) hosts;
  the host must resolve to public addresses only (no localhost, LAN, cloud metadata). Every redirect is checked
  again, at most 4 hops.
- Only documents we read anyway (PDF, Office, CSV/TXT, HTML, ZIP via the safe archive reader); never programs or
  scripts (by type or by name). Size cap 8 MB, read as a stream; 5 s per link, 3 links, 10 s for all of them.
- No cookies kept, nothing sent but a GET with a generic user agent. An unsafe or failing link is skipped and
  logged: the quote goes on from the mail. LINK_READ=off disables it.
"""
import ipaddress
import os
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

ON = os.environ.get("LINK_READ", "on").lower() != "off"
MAX_LINKS, MAX_BYTES, MAX_HOPS = 3, 8_000_000, 4
TIMEOUT_S, BUDGET_S = 5.0, 10.0
URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'()\[\]{}]+", re.I)
RISKY = (".exe", ".js", ".scr", ".bat", ".cmd", ".vbs", ".ps1", ".msi", ".lnk", ".com", ".jar", ".docm", ".xlsm",
         ".pptm", ".iso", ".apk", ".dmg", ".pkg", ".sh", ".hta", ".dll", ".app", ".reg")
TYPES = {"application/pdf": "pdf", "text/html": "html", "application/xhtml+xml": "html", "text/plain": "txt",
         "text/csv": "csv", "application/csv": "csv", "application/zip": "zip", "application/x-zip-compressed": "zip",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
         "application/vnd.ms-excel": "xls", "application/vnd.oasis.opendocument.spreadsheet": "ods",
         "application/vnd.oasis.opendocument.text": "odt", "application/rtf": "rtf", "text/rtf": "rtf"}
DOCS = set(TYPES.values()) | {"htm", "tsv"}
# share pages → the file itself (the share page needs JavaScript; the download link doesn't)
SHARES = [
    (re.compile(r"^https://drive\.google\.com/file/d/([\w-]+).*$"), r"https://drive.google.com/uc?export=download&id=\1"),
    (re.compile(r"^https://docs\.google\.com/spreadsheets/d/([\w-]+).*$"), r"https://docs.google.com/spreadsheets/d/\1/export?format=xlsx"),
    (re.compile(r"^https://docs\.google\.com/document/d/([\w-]+).*$"), r"https://docs.google.com/document/d/\1/export?format=docx"),
    (re.compile(r"^(https://(?:www\.)?dropbox\.com/[^?#]+).*$"), r"\1?dl=1"),
    # OneDrive / SharePoint share links download with download=1 (the viewer needs JavaScript)
    (re.compile(r"^(https://(?:[\w-]+\.sharepoint\.com|onedrive\.live\.com)/[^?#]+)(?:\?([^#]*?))?(?:&?download=1)?(?:#.*)?$"),
     r"\1?\2&download=1"),
]
POPUP = re.compile(r"cookie|consent|gdpr|modal|popup|pop-up|newsletter|overlay|subscribe|banner|lightbox", re.I)


def find(text: str) -> list[str]:
    out = []
    for raw in URL.findall(text or ""):
        url = raw.rstrip(".,;:!?")
        url = url if url.lower().startswith("http") else "https://" + url
        if url not in out:
            out.append(url)
    return out[:MAX_LINKS]


def direct(url: str) -> str:
    for pattern, target in SHARES:
        if pattern.match(url):
            return pattern.sub(target, url, count=1)
    return url


def _public(host: str, resolve=socket.getaddrinfo) -> bool:
    try:
        addresses = {info[4][0] for info in resolve(host, None)}
    except OSError:
        return False
    return bool(addresses) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses)


def unsafe(url: str, resolve=socket.getaddrinfo) -> str | None:
    """Why this link is not opened, or None."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "not a valid address"
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https"):
        return f"{parts.scheme or 'no'} scheme"
    if parts.username or parts.password or "@" in parts.netloc:
        return "user name or password in the address (a phishing trick)"
    if port not in (None, 80, 443):
        return f"unusual port {port}"
    if not host or "." not in host:
        return "no proper host name"
    try:
        ipaddress.ip_address(host.strip("[]"))
        return "a bare IP address instead of a site name"
    except ValueError:
        pass
    if any(label.startswith("xn--") for label in host.split(".")):
        return "look-alike (punycode) site name"
    if parts.path.lower().endswith(RISKY):
        return "a program or script, never opened"
    # shortcut: the name is resolved here and again by httpx (DNS rebinding window); pin the IP if this ever matters
    if not _public(host, resolve):
        return "the site is not on the public internet (or doesn't exist)"
    return None


class _Text(HTMLParser):
    """Visible text of a page; scripts, styles, frames and popup/cookie/newsletter overlays (with everything inside
    them) are dropped, so nothing on the page can act or get in the way."""
    SKIP = {"script", "style", "noscript", "iframe", "template", "svg", "object", "embed", "dialog", "head", "button"}
    VOID = {"br", "img", "input", "meta", "link", "hr", "area", "base", "col", "source", "wbr"}
    BLOCK = {"p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skipping, self.login = [], [], False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "input" and a.get("type", "").lower() == "password":
            self.login = True
        if tag in self.VOID:
            if tag == "br" and not self.skipping:
                self.out.append("\n")
            return
        if self.skipping:
            self.skipping.append(tag)
        elif tag in self.SKIP or a.get("aria-modal") == "true" or a.get("role") in ("dialog", "alertdialog") \
                or POPUP.search(" ".join([a.get("class", ""), a.get("id", "")])):
            self.skipping.append(tag)

    def handle_endtag(self, tag):
        if self.skipping:
            if tag in self.skipping:  # close up to the matching tag (tolerates unclosed children)
                while self.skipping and self.skipping.pop() != tag:
                    pass
            return
        if tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.out.append(data)


def clean_html(page: str) -> str | None:
    """The page's visible text without popups; None for a login page (we never sign in anywhere)."""
    parser = _Text()
    parser.feed(page)
    parser.close()
    if parser.login:
        return None
    lines = (re.sub(r"[ \t]+", " ", line).strip(" |") for line in "".join(parser.out).splitlines())
    return "\n".join(line for line in lines if line)


def fetch(url: str, client: httpx.Client, resolve=socket.getaddrinfo, timeout: float = TIMEOUT_S) -> tuple[str, bytes]:
    """(file name with the right extension, content). Raises ValueError with the reason when it isn't read."""
    url, started = direct(url), time.monotonic()
    for _ in range(MAX_HOPS + 1):
        if reason := unsafe(url, resolve):
            raise ValueError(reason)
        left = timeout - (time.monotonic() - started)
        if left <= 0:
            raise ValueError("too slow")
        with client.stream("GET", url, timeout=left, follow_redirects=False,
                           headers={"User-Agent": "Mozilla/5.0 (freight quote reader)", "Accept": "*/*"}) as response:
            if response.is_redirect and response.headers.get("location"):
                url = urljoin(url, response.headers["location"])
                continue
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
            name = urlsplit(url).path.rsplit("/", 1)[-1] or "page"
            disposition = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", response.headers.get("content-disposition", ""), re.I)
            if disposition:
                name = disposition.group(1)
            if name.lower().endswith(RISKY):
                raise ValueError("a program or script, never opened")
            ext = TYPES.get(kind) or (name.rsplit(".", 1)[-1].lower() if "." in name else "")
            if ext not in DOCS:
                raise ValueError(f"not a document ({kind or 'no type'})")
            if int(response.headers.get("content-length") or 0) > MAX_BYTES:
                raise ValueError("larger than 8 MB")
            data = b""
            for chunk in response.iter_bytes():
                data += chunk
                if len(data) > MAX_BYTES:
                    raise ValueError("larger than 8 MB")
                if time.monotonic() - started > timeout:
                    raise ValueError("too slow")
            if ext in ("html", "htm"):
                page = clean_html(data.decode(response.encoding or "utf-8", errors="replace"))
                if page is None:
                    raise ValueError("a login page (we never sign in anywhere)")
                data, ext = page.encode(), "txt"
            stem = re.sub(r"[^\w.-]", "_", name.rsplit(".", 1)[0])[:60] or "link"
            return f"{stem}.{ext}", data
    raise ValueError("too many redirects")


def read_all(text: str, to_text, client: httpx.Client | None = None, resolve=socket.getaddrinfo,
             budget: float = BUDGET_S) -> list[tuple[str, str, str]]:
    """[(url, text or "", note)] for the links in `text`. `to_text(filename, data)` is the attachment reader."""
    if not ON:
        return []
    out, deadline = [], time.monotonic() + budget
    own = client is None
    client = client or httpx.Client()
    try:
        for url in find(text):
            left = deadline - time.monotonic()
            if left < 1:
                out.append((url, "", "skipped: the link time budget is used up"))
                continue
            try:
                name, data = fetch(url, client, resolve, min(TIMEOUT_S, left))
                body = to_text(name, data) or ""
                out.append((url, body, f"read as {name}: {len(body)} characters"))
            except (ValueError, httpx.HTTPError, OSError) as error:
                out.append((url, "", f"not opened: {error}"))
    finally:
        if own:
            client.close()
    return out
