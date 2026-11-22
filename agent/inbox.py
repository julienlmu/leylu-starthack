"""Mailbox adapters. The agents only use fetch(), reply(), send() and attachment(), so FiveUMailbox (live)
and FixtureMailbox (tests, local runs) are interchangeable.

A mail is a dict: id, thread_id, from, to, subject, body, received_at, attachments [{id, filename, …}].
thread_id is the id of the thread's first mail, so a customer's replies map to the session of their RFQ
and a carrier's reply maps to the bid request we sent.
"""

import base64
import contextlib
import fcntl
import html
import tempfile
import itertools
import json
import os
import re
import time
import unicodedata
from pathlib import Path

import httpx

FIVEU_BASE_URL = os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai")
MAX_429_RETRIES = 6
# A 502 / timeout on the mailbox: a read (GET) is retried briefly. A send (POST) is retried only when it never reached
# 5U (no connection made): a 502 / 5xx / read timeout may mean 5U has it, 5U has no "sent" list to check, and the quote
# must never go out twice.
NOT_DELIVERED = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
TRANSIENT_RETRIES = int(os.environ.get("MAILBOX_TRANSIENT_RETRIES", "2"))
# 5U: one mailbox poll per 5 s per team key, else a 22.5-point penalty (round 48). The gap is counted from the END of
# the last poll to the START of the next, so even a slow response never puts two polls < 5 s apart at 5U. Shared by
# every process on this machine (worker, setup_5u, probe) through a lock file. Never below 5.5 s, whatever is set.
POLL_GAP_SECONDS = max(5.5, float(os.environ.get("POLL_GAP_SECONDS", "6")))
POLL_GAP_FILE = Path(os.environ.get("POLL_GAP_FILE", Path(tempfile.gettempdir()) / "leylu-5u-mailbox-poll"))


@contextlib.contextmanager
def poll_slot():
    """Waits until POLL_GAP_SECONDS have passed since the last mailbox poll ended (any process), then holds the slot
    for this poll; the poll's end time is recorded even if it fails."""
    with open(POLL_GAP_FILE, "a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0)
            try:
                last = float(handle.read().strip() or 0)
            except ValueError:
                last = 0.0
            if (wait := last + POLL_GAP_SECONDS - time.time()) > 0:
                time.sleep(min(wait, POLL_GAP_SECONDS))  # a clock jump never blocks longer than one gap
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.write(str(time.time()))
            handle.flush()
            fcntl.flock(handle, fcntl.LOCK_UN)


def _re(subject: str) -> str:
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


# Replies quote our own mail below theirs; only the new text counts ("…we'll book it", "Total: 1234.00 EUR" are ours).
QUOTED = re.compile(r"^(>|On .+ wrote:|Am .+ schrieb|Le .+ a écrit|El .+ escribió|-----Original|From:|Von:)", re.I)


def latest_text(body: str) -> str:
    """The new part of a reply: everything above the first quoted line."""
    lines = []
    for line in body.splitlines():
        if QUOTED.match(line.strip()):
            break
        lines.append(line)
    return "\n".join(lines)


def mail_data(mail: dict) -> dict:
    """Event data of a mail event: the fields the Sessions UI shows in the thread."""
    return {key: mail.get(key) for key in ("from", "to", "subject", "body")}


def reply_data(mail: dict, body: str) -> dict:
    """Event data of our reply to `mail`: from our mailbox (where the mail was sent to) back to its sender."""
    return {"from": mail.get("to"), "to": mail["from"], "subject": _re(mail["subject"]), "body": body}


# HACKATHON_GAPS #2: "U\u200bN1133" (zero-width space), "FRА" (Cyrillic A), "７１５ kg" (full-width), "٧١٥ kg" (Arabic-Indic):
# every rule and the extraction see plain text. Look-alikes are mapped only inside a word that also has Latin letters,
# so a real Russian or Greek mail keeps its letters.
INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u180e\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\ufeff"))
HOMOGLYPHS = str.maketrans("АВЕКМНОРСТХаеорсухіјѕԁԛԝΑΒΕΖΗΙΚΜΝΟΡΤΥΧοα", "ABEKMHOPCTXaeopcyxijsdqwABEZHIKMNOPTYXoa")
MIXED_WORD = re.compile(r"\w*[A-Za-z]\w*")
# TEXT_SHAPES (on): what NFKC leaves. LLM-written mails use U+2011 non-breaking hyphens ("time‑critical", "2026‑12‑04",
# "non‑dangerous") and en dashes, which no rule's "-" matched; "1’250 kg" / "We’ll" curly apostrophes; an HTML body
# ("<p>UN&nbsp;3480</p>", "&#8209;") hid every word behind tags and entities. All become plain text first.
TEXT_SHAPES = os.environ.get("TEXT_SHAPES", "on").lower() != "off"
DASHES = str.maketrans({c: "-" for c in "‐‑‒–—―⁃−﹘﹣－"} |
                       {c: "'" for c in "‘’‚‛′´ʼ"} | {c: '"' for c in "“”„‟″"})
HTML_TAG = re.compile(r"</?(?:p|br|div|span|table|thead|tbody|tr|td|th|li|ul|ol|b|i|u|strong|em|font|html|head|body|h[1-6]|"
                      r"a|img|meta|style|o:p)\b[^>]*>", re.I)
HTML_ENTITY = re.compile(r"&(?:nbsp|amp|lt|gt|quot|apos|ndash|mdash|shy|#\d{2,6}|#x[0-9a-f]{2,5});", re.I)


def _html_text(text: str) -> str:
    """An HTML body as text: line breaks where blocks end, cells apart, no tags, entities decoded."""
    if not (HTML_TAG.search(text) or HTML_ENTITY.search(text)):
        return text
    text = re.sub(r"(?is)<(style|head)\b.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(?:p|div|tr|li|h[1-6]|table)>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", " | ", text)
    return html.unescape(HTML_TAG.sub("", text))


# "2k EUR", "1.5k kg", "2,5k", "3 Tsd.", "2 thousand", "1.2 Mio": written out, so every number reader (bids, budget,
# grounding, units) and the model see 2000 / 1500 / 2500 / 3000 / 1200000. Never "kg", "2K-Lack", "1.2 m".
ABBREVIATED = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d{1,3})?)\s?(k|K|Tsd\.?|tsd\.?|Tausend|tausend|thousand|Mio\.?|"
                         r"[Mm]illion(?:s|en)?|mn)(?![\w-])")


def _expand(m: re.Match) -> str:
    number = float(m[1].replace(",", "."))
    value = number * (1_000_000 if m[2][0] in "Mm" else 1000)
    return f"{value:.0f}" if value == int(value) else f"{value:g}"


def normalize(text: str) -> str:
    if not text:
        return text or ""
    if TEXT_SHAPES:
        text = _html_text(text)
    text = unicodedata.normalize("NFKC", text).translate(INVISIBLE)
    if TEXT_SHAPES:
        text = text.translate(DASHES)
    text = "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() and unicodedata.digit(c, None) is not None
                   else c for c in text)
    text = MIXED_WORD.sub(lambda m: m.group(0).translate(HOMOGLYPHS) if not m.group(0).isascii() else m.group(0), text)
    return ABBREVIATED.sub(_expand, text)


class FiveUMailbox:
    """The team mailbox at 5U (API docs: {FIVEU_BASE_URL}/docs). Poll every second or two: response time counts.

    The last seen mail id is kept in a file, so a restart neither misses nor re-answers mail.
    """

    def __init__(self, key: str | None = None, state_file: str = os.environ.get("SINCE_ID_FILE", ".since_id")):
        key = key or os.environ["FIVEU_API_KEY"]
        self.http = httpx.Client(base_url=FIVEU_BASE_URL, headers={"X-API-Key": key}, timeout=15)
        self.state = Path(state_file)
        self.since_id = int(self.state.read_text()) if self.state.exists() else 0

    def fetch(self) -> list[dict]:
        with poll_slot():  # never retried here: a 429 waits for the next slot, never a quick second poll
            response = self.http.get("/v1/mailbox/messages", params={"since_id": self.since_id, "limit": 200})
        response.raise_for_status()
        data = response.json()
        self.since_id = data["next_since_id"]
        self.state.write_text(str(self.since_id))
        return [self._mail(item) for item in data["messages"]]

    def get(self, message_id) -> dict:
        """One mail by id: an RFQ resumed after a restart (the poll has already moved past it)."""
        response = self._call("GET", f"/v1/mailbox/messages/{message_id}")
        return self._mail(response.json())

    def reply(self, mail: dict, body: str, subject: str | None = None, attachments: list | None = None) -> int:
        """Answers in the mail's thread (in_reply_to): only our first quote in a customer thread counts.
        attachments: [{"filename", "content_base64"}] (5U: pdf/xlsx/…, max 5 × 10 MB)."""
        message = {"to": mail["from"], "subject": subject or _re(mail["subject"]), "body": body, "in_reply_to": mail["id"]}
        if attachments:
            try:
                return self._send({**message, "attachments": attachments})
            except httpx.HTTPStatusError as error:  # 5U refused the attachment (shape, size): the quote still goes out
                if error.response.status_code not in (400, 413, 415, 422):
                    raise
                print(f"attachment refused ({error.response.status_code}): reply sent without it")
        return self._send(message)

    def send(self, to: str, subject: str, body: str) -> int:
        """Starts a new thread, e.g. a bid request. Returns its id, which is the thread id of the replies."""
        return self._send({"to": to, "subject": subject, "body": body})

    def attachment(self, mail: dict, attachment: dict) -> bytes:
        response = self._call("GET", f"/v1/mailbox/messages/{mail['id']}/attachments/{attachment['id']}")
        return response.content

    def _send(self, message: dict) -> int:
        return self._call("POST", "/v1/mailbox/messages", json=message).json()["id"]

    def _call(self, method: str, url: str, **kwargs) -> httpx.Response:
        """One request; a 429 ("one poll per 5 seconds", since ~20:45) waits `retry_after` and tries again, so an
        attachment or a quote is never lost to the rate limit."""
        transient = 0
        for _ in range(MAX_429_RETRIES + TRANSIENT_RETRIES):
            try:
                response = self.http.request(method, url, **kwargs)
            except httpx.TransportError as error:  # connection reset, timeout: once or twice more, then give up
                if transient >= TRANSIENT_RETRIES or (method != "GET" and not isinstance(error, NOT_DELIVERED)):
                    raise
                transient += 1
                print(f"mailbox {method} {url}: {type(error).__name__}, retry {transient}")
                time.sleep(POLL_GAP_SECONDS)  # 5U counts every call like a poll: never two within 5 s
                continue
            if response.status_code >= 500 and method == "GET" and transient < TRANSIENT_RETRIES:
                transient += 1
                print(f"mailbox {method} {url}: HTTP {response.status_code}, retry {transient}")
                time.sleep(POLL_GAP_SECONDS)
                continue
            if response.status_code != 429:
                break
            try:
                wait = float(response.json().get("retry_after") or 1)
            except ValueError:
                wait = 1.0
            time.sleep(min(max(wait, 0.5), 5))
        response.raise_for_status()
        return response

    @staticmethod
    def _mail(item: dict) -> dict:
        # shortcut: field names read from the API docs' prose (the poll item has no schema);
        # check them with `uv run python inbox.py` and adjust here if 5U names them differently.
        references = item.get("references") or []
        return {
            "id": item["id"],
            "thread_id": references[0] if references else item["id"],
            "from": item.get("from") or item.get("sender") or "",
            "to": item.get("to") or "",
            "subject": normalize(item.get("subject") or ""),  # every mail, also one fetched again by id (resume)
            "body": normalize(item.get("body") or ""),
            "received_at": item.get("sent_at") or item.get("created_at") or item.get("received_at"),
            "attachments": item.get("attachments") or [],
        }


class FixtureMailbox:
    """Reads mails from JSON files in a folder and records what we send (tests and local runs)."""

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.seen: set[str] = set()
        self.sent: list[dict] = []
        self._ids = itertools.count(1)  # next() is atomic: parallel RFQ threads never get the same thread id

    def fetch(self) -> list[dict]:
        """New mails since the last call. Dropping a JSON file into the folder delivers it."""
        new = []
        for path in sorted(self.folder.glob("*.json")):
            if path.name not in self.seen:
                self.seen.add(path.name)
                new.append(json.loads(path.read_text()))
        return new

    def get(self, message_id) -> dict:
        return next(m for m in (json.loads(p.read_text()) for p in sorted(self.folder.glob("*.json")))
                    if str(m["id"]) == str(message_id))

    def reply(self, mail: dict, body: str, subject: str | None = None, attachments: list | None = None) -> str:
        return self._record({"to": mail["from"], "thread_id": mail["thread_id"], "subject": subject or _re(mail["subject"]),
                             "body": body, **({"attachments": attachments} if attachments else {})})

    def send(self, to: str, subject: str, body: str) -> str:
        return self._record({"to": to, "thread_id": f"out-{next(self._ids)}", "subject": subject, "body": body})

    def _record(self, mail: dict) -> str:
        """Keeps the mail instead of sending it, and prints it so a local run shows what would go out."""
        self.sent.append(mail)
        print(f"\n[not sent] to {mail['to']} | {mail['subject']}\n{mail['body']}\n")
        return mail["thread_id"]

    def attachment(self, mail: dict, attachment: dict) -> bytes:
        return base64.b64decode(attachment["content_base64"])


if __name__ == "__main__":
    # Probe: print the first raw mails, to check the field names _mail() relies on.
    with poll_slot():
        probe = httpx.get(f"{FIVEU_BASE_URL}/v1/mailbox/messages", params={"since_id": 0, "limit": 3},
                          headers={"X-API-Key": os.environ["FIVEU_API_KEY"]}, timeout=15)
    print(probe.status_code, json.dumps(probe.json(), indent=2, ensure_ascii=False)[:4000])
