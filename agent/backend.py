"""HTTP client for the backend (endpoints and shapes: docs/CONTRACT.md, proposal in docs/PLAN.md §7)."""

import os
from datetime import datetime, timezone

import httpx


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Backend:
    def __init__(self, url: str = os.environ.get("BACKEND_URL", "http://localhost:8000")):
        self.http = httpx.Client(base_url=url, timeout=10)

    def _json(self, response: httpx.Response):
        response.raise_for_status()
        return response.json()

    def create_session(self, customer: str, thread_id: str) -> int:
        return self._json(self.http.post("/api/sessions", json={"customer": customer, "thread_id": thread_id}))["id"]

    def session(self, session_id: int) -> dict:
        return self._json(self.http.get(f"/api/sessions/{session_id}"))

    def find(self, thread_id: str) -> dict | None:
        return self._json(self.http.get("/api/sessions/find", params={"thread_id": thread_id}))

    def update(self, session_id: int, **fields) -> None:
        self._json(self.http.patch(f"/api/sessions/{session_id}", json=fields))

    def event(self, session_id: int, kind: str, text: str, data: dict | None = None, cost: float = 0.0) -> None:
        event = {"session_id": session_id, "at": now(), "kind": kind, "text": text,
                 "data": data or {}, "llm_cost_usd": cost}
        self._json(self.http.post(f"/api/sessions/{session_id}/events", json=event))

    def price(self, rfq: dict, bids: list[dict] | None = None) -> dict:
        return self._json(self.http.post("/api/price", json={"rfq": rfq, "bids": bids or []}))
