"""Mailbox adapters. The agents only use fetch(), reply() and send(), so the real 5U mailbox
adapter can replace FixtureMailbox without touching them.

A mail is a dict: id, thread_id, from, to, subject, body, received_at,
attachments [{filename, content_base64}].
"""

import json
from pathlib import Path


class FixtureMailbox:
    """Reads mails from JSON files in a folder and records what we send.

    shortcut: stand-in until the 5U mailbox Swagger (kit card, task U1) is known; then add the API adapter.
    """

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

    def reply(self, mail: dict, body: str) -> None:
        """Answer in the mail's own thread: only our first quote in a customer thread counts."""
        subject = mail["subject"] if mail["subject"].lower().startswith("re:") else "Re: " + mail["subject"]
        self.sent.append({"to": mail["from"], "thread_id": mail["thread_id"], "subject": subject, "body": body})

    def send(self, to: str, subject: str, body: str) -> str:
        """Start a new thread, e.g. a bid request to a carrier. Returns its thread id to match the replies."""
        thread_id = f"out-{len(self.sent) + 1}"
        self.sent.append({"to": to, "thread_id": thread_id, "subject": subject, "body": body})
        return thread_id
