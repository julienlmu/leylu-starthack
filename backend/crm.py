"""CRM store: sessions (one per customer request) and their events, in SQLite. Shapes: docs/CONTRACT.md."""

import json
import sqlite3
from datetime import datetime, timezone

# Session fields stored as JSON text, with their empty value.
JSON_FIELDS = {"rfq": None, "bids": [], "quote": None, "booking": None, "status_updates": []}
PLAIN_FIELDS = ("stage", "outcome", "llm_cost_usd", "needs_human", "paused")
PATCHABLE = (*PLAIN_FIELDS, *JSON_FIELDS)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'new',
    outcome TEXT NOT NULL DEFAULT 'open',
    rfq TEXT, bids TEXT, quote TEXT, booking TEXT, status_updates TEXT,
    llm_cost_usd REAL NOT NULL DEFAULT 0,
    needs_human INTEGER NOT NULL DEFAULT 0,
    paused INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS sessions_thread ON sessions(thread_id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    llm_cost_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS events_session ON events(session_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Crm:
    def __init__(self, path: str):
        # One connection for the app; FastAPI runs the async endpoints on one event loop thread.
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    # --- sessions ---
    def create_session(self, customer: str, thread_id: str, received_at: str | None = None) -> int:
        at = now()
        cur = self.db.execute(
            "INSERT INTO sessions (customer, thread_id, received_at, updated_at) VALUES (?, ?, ?, ?)",
            (customer, str(thread_id), received_at or at, at))
        self.db.commit()
        return cur.lastrowid

    def session(self, session_id: int) -> dict | None:
        row = self.db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return _session(row) if row else None

    def sessions(self) -> list[dict]:
        return [_session(r) for r in self.db.execute("SELECT * FROM sessions ORDER BY id DESC")]

    def update(self, session_id: int, fields: dict) -> dict | None:
        """Replaces each given field (no deep merge). Unknown fields are ignored.

        null resets a list field to [] and an object field to null; null for stage, outcome, cost or a flag is ignored.
        """
        fields = {k: (JSON_FIELDS[k] if v is None and k in JSON_FIELDS else v) for k, v in fields.items()
                  if k in PATCHABLE and not (v is None and k in PLAIN_FIELDS)}
        if fields:
            values = [json.dumps(v) if k in JSON_FIELDS else v for k, v in fields.items()]
            sets = ", ".join(f"{k} = ?" for k in fields)
            self.db.execute(f"UPDATE sessions SET {sets}, updated_at = ? WHERE id = ?",
                            (*values, now(), session_id))
            self.db.commit()
        return self.session(session_id)

    def find(self, thread_id: str | None = None, reference: str | None = None) -> dict | None:
        """Newest session for a thread, or for a booking ref / rate ID / customer reference (any case)."""
        if thread_id is not None:
            row = self.db.execute("SELECT * FROM sessions WHERE thread_id = ? ORDER BY id DESC LIMIT 1",
                                  (str(thread_id),)).fetchone()
            return _session(row) if row else None
        if not reference:
            return None
        ref = reference.strip().lower()
        for s in self.sessions():
            booking, quote, rfq = s["booking"] or {}, s["quote"] or {}, s["rfq"] or {}
            candidates = (booking.get("booking_reference"), booking.get("rate_id"), quote.get("rate_id"),
                          rfq.get("customer_reference"))
            if any(c and str(c).strip().lower() == ref for c in candidates):
                return s
        return None

    def search(self, q: str | None = None, stage: str | None = None, needs_human: bool | None = None) -> list[dict]:
        found = self.sessions()
        if stage:
            found = [s for s in found if s["stage"] == stage]
        if needs_human is not None:
            found = [s for s in found if s["needs_human"] == needs_human]
        if q and (q := q.strip().lower()):
            found = [s for s in found if q.lstrip("#") == str(s["id"]) or q in _haystack(s)]
        return found

    # --- events ---
    def add_event(self, event: dict) -> dict:
        event = {"session_id": event.get("session_id"), "at": event.get("at") or now(),
                 "kind": event["kind"], "text": event.get("text", ""), "data": event.get("data") or {},
                 "llm_cost_usd": event.get("llm_cost_usd") or 0}
        self.db.execute("INSERT INTO events (session_id, at, kind, text, data, llm_cost_usd) VALUES (?, ?, ?, ?, ?, ?)",
                        (event["session_id"], event["at"], event["kind"], event["text"],
                         json.dumps(event["data"]), event["llm_cost_usd"]))
        if event["session_id"] is not None:
            self.db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now(), event["session_id"]))
        self.db.commit()
        return event

    def events(self, session_id: int) -> list[dict]:
        rows = self.db.execute("SELECT * FROM events WHERE session_id = ? ORDER BY id", (session_id,))
        return [{"session_id": r["session_id"], "at": r["at"], "kind": r["kind"], "text": r["text"],
                 "data": json.loads(r["data"]), "llm_cost_usd": r["llm_cost_usd"]} for r in rows]


def _session(row: sqlite3.Row) -> dict:
    s = dict(row)
    for field, empty in JSON_FIELDS.items():
        s[field] = json.loads(s[field]) if s[field] is not None else empty
    s["needs_human"], s["paused"] = bool(s["needs_human"]), bool(s["paused"])
    if s["thread_id"].isdigit():  # 5U mail ids are integers: give them back as sent, the agent replies with them
        s["thread_id"] = int(s["thread_id"])
    return s


def _haystack(s: dict) -> str:
    rfq, quote, booking = (x if isinstance(x, dict) else {} for x in (s["rfq"], s["quote"], s["booking"]))
    parts = [s["customer"], s["thread_id"], rfq.get("origin"), rfq.get("destination"), rfq.get("customer_reference"),
             rfq.get("commodity"), quote.get("carrier"), quote.get("rate_id"), booking.get("booking_reference"),
             booking.get("rate_id"), booking.get("airline"), *(b.get("carrier") for b in s["bids"] if isinstance(b, dict))]
    return " ".join(str(p) for p in parts if p).lower()
