"""Mailbox adapters. The agents only use fetch(), reply(), send() and attachment(), so FiveUMailbox (live)
and FixtureMailbox (tests, local runs) are interchangeable.

A mail is a dict: id, thread_id, from, to, subject, body, received_at, attachments [{id, filename, …}].
thread_id is the id of the thread's first mail, so a customer's replies map to the session of their RFQ
and a carrier's reply maps to the bid request we sent.
"""

import base64
import json
import os
from pathlib import Path

import httpx

FIVEU_BASE_URL = os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai")


def _re(subject: str) -> str:
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


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
        response = self.http.get("/v1/mailbox/messages", params={"since_id": self.since_id, "limit": 200})
        response.raise_for_status()
        data = response.json()
        self.since_id = data["next_since_id"]
        self.state.write_text(str(self.since_id))
        return [self._mail(item) for item in data["messages"]]

    def reply(self, mail: dict, body: str) -> int:
        """Answers in the mail's thread (in_reply_to): only our first quote in a customer thread counts."""
        return self._send({"to": mail["from"], "subject": _re(mail["subject"]), "body": body, "in_reply_to": mail["id"]})

    def send(self, to: str, subject: str, body: str) -> int:
        """Starts a new thread, e.g. a bid request. Returns its id, which is the thread id of the replies."""
        return self._send({"to": to, "subject": subject, "body": body})

    def attachment(self, mail: dict, attachment: dict) -> bytes:
        response = self.http.get(f"/v1/mailbox/messages/{mail['id']}/attachments/{attachment['id']}")
        response.raise_for_status()
        return response.content

    def _send(self, message: dict) -> int:
        response = self.http.post("/v1/mailbox/messages", json=message)
        response.raise_for_status()
        return response.json()["id"]

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
            "subject": item.get("subject") or "",
            "body": item.get("body") or "",
            "received_at": item.get("sent_at") or item.get("created_at") or item.get("received_at"),
            "attachments": item.get("attachments") or [],
        }


class FixtureMailbox:
    """Reads mails from JSON files in a folder and records what we send (tests and local runs)."""

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.seen: set[str] = set()
        self.sent: list[dict] = []

    def fetch(self) -> list[dict]:
        """New mails since the last call. Dropping a JSON file into the folder delivers it."""
        new = []
        for path in sorted(self.folder.glob("*.json")):
            if path.name not in self.seen:
                self.seen.add(path.name)
                new.append(json.loads(path.read_text()))
        return new

    def reply(self, mail: dict, body: str) -> str:
        return self._record({"to": mail["from"], "thread_id": mail["thread_id"], "subject": _re(mail["subject"]),
                             "body": body})

    def send(self, to: str, subject: str, body: str) -> str:
        return self._record({"to": to, "thread_id": f"out-{len(self.sent) + 1}", "subject": subject, "body": body})

    def _record(self, mail: dict) -> str:
        """Keeps the mail instead of sending it, and prints it so a local run shows what would go out."""
        self.sent.append(mail)
        print(f"\n[not sent] to {mail['to']} | {mail['subject']}\n{mail['body']}\n")
        return mail["thread_id"]

    def attachment(self, mail: dict, attachment: dict) -> bytes:
        return base64.b64decode(attachment["content_base64"])


if __name__ == "__main__":
    # Probe: print the first raw mails, to check the field names _mail() relies on.
    probe = httpx.get(f"{FIVEU_BASE_URL}/v1/mailbox/messages", params={"since_id": 0, "limit": 3},
                      headers={"X-API-Key": os.environ["FIVEU_API_KEY"]}, timeout=15)
    print(probe.status_code, json.dumps(probe.json(), indent=2, ensure_ascii=False)[:4000])
