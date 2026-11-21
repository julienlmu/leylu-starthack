"""Sends a person's reply from the Sessions UI (intervene `send`) through the 5U mailbox. The agent owns all other mail."""

import os

import httpx


class FiveUMailbox:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url or os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai")
        self.api_key = api_key or os.environ.get("FIVEU_API_KEY", "")

    async def reply(self, to: str, subject: str, body: str, in_reply_to) -> dict:
        """Replies in the thread of mail `in_reply_to` (5U ids are integers). Returns the stored mail."""
        if not self.api_key:
            raise RuntimeError("FIVEU_API_KEY is not set: the backend can't send mail")
        message = {"to": to, "subject": subject, "body": body,
                   "in_reply_to": int(in_reply_to) if str(in_reply_to).isdigit() else in_reply_to}
        async with httpx.AsyncClient(base_url=self.base_url, headers={"X-API-Key": self.api_key}, timeout=15) as http:
            response = await http.post("/v1/mailbox/messages", json=message)
            response.raise_for_status()
            return response.json()
