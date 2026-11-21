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

    def create_session(self, customer: str, thread_id, received_at: str | None = None) -> int:
        """received_at: when 5U sent the mail; response time counts from there."""
        body = {"customer": customer, "thread_id": thread_id, "received_at": received_at}
        return self._json(self.http.post("/api/sessions", json={k: v for k, v in body.items() if v is not None}))["id"]

    def session(self, session_id: int) -> dict:
        return self._json(self.http.get(f"/api/sessions/{session_id}"))

    def find(self, thread_id=None, reference: str | None = None) -> dict | None:
        """The session for a mail thread, or for a reference (booking BK-…, rate ID, customer reference)."""
        params = {k: v for k, v in {"thread_id": thread_id, "reference": reference}.items() if v is not None}
        return self._json(self.http.get("/api/sessions/find", params=params))

    def booked_sessions(self) -> list[dict]:
        """Every session with a booking (tracking questions that name no reference are matched against these)."""
        return [s for s in self._json(self.http.get("/api/sessions")) if s.get("booking")]

    def update(self, session_id: int, **fields) -> None:
        self._json(self.http.patch(f"/api/sessions/{session_id}", json=fields))

    def event(self, session_id: int, kind: str, text: str, data: dict | None = None, cost: float = 0.0) -> None:
        event = {"session_id": session_id, "at": now(), "kind": kind, "text": text,
                 "data": data or {}, "llm_cost_usd": cost}
        self._json(self.http.post(f"/api/sessions/{session_id}/events", json=event))

    def book(self, session_id: int, rate_id: str | None) -> dict:
        """Books the quoted option (portal booking by rate ID); returns the booking (booking_reference, airline, …)."""
        return self._json(self.http.post("/api/book", json={"session_id": session_id, "rate_id": rate_id}, timeout=40))

    def ingest_tariff(self, filename: str, content_base64: str, sender: str) -> dict:
        return self._json(self.http.post("/api/tariffs/ingest",
                                         json={"filename": filename, "content_base64": content_base64, "from": sender}))

    def price(self, rfq: dict, bids: list[dict] | None = None) -> dict:
        return self._json(self.http.post("/api/price", json={"rfq": rfq, "bids": bids or []}, timeout=30))
