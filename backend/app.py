"""Backend API: CRM sessions, events, intervene and the live SSE stream. Contract: docs/CONTRACT.md.

Run: `uv run uvicorn app:app --port 8000` (from backend/), or `make backend` from the repo root.
"""

import os
from pathlib import Path
from typing import Literal

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from crm import Crm
from mailbox import FiveUMailbox
from stream import Broadcaster

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "crm.sqlite3"))


class SessionIn(BaseModel):
    customer: str
    thread_id: str | int
    received_at: str | None = None


class EventIn(BaseModel):
    session_id: int | None = None
    at: str | None = None
    kind: str
    text: str = ""
    data: dict = {}
    llm_cost_usd: float = 0


class InterveneIn(BaseModel):
    action: Literal["pause", "resume", "send"]
    body: str = ""


def create_app(crm: Crm | None = None, mailbox: FiveUMailbox | None = None) -> FastAPI:
    crm = crm or Crm(DB_PATH)
    mailbox = mailbox or FiveUMailbox()
    hub = Broadcaster()
    app = FastAPI(title="leylu forwarder backend")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.crm, app.state.hub = crm, hub

    def get(session_id: int) -> dict:
        session = crm.session(session_id)
        if session is None:
            raise HTTPException(404, f"no session {session_id}")
        return session

    def log(event: dict) -> dict:
        stored = crm.add_event(event)
        hub.publish(stored)
        return stored

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/api/sessions")
    async def create_session(body: SessionIn):
        return {"id": crm.create_session(body.customer, str(body.thread_id), body.received_at)}

    @app.get("/api/sessions")
    async def list_sessions(q: str | None = None, stage: str | None = None, needs_human: bool | None = None):
        return crm.search(q, stage, needs_human)

    # Before /api/sessions/{session_id}, so "find" is not read as an id.
    @app.get("/api/sessions/find")
    async def find_session(thread_id: str | None = None, reference: str | None = None):
        return crm.find(thread_id, reference)

    @app.get("/api/sessions/{session_id}")
    async def read_session(session_id: int):
        return get(session_id)

    @app.patch("/api/sessions/{session_id}")
    async def update_session(session_id: int, fields: dict = Body(...)):
        get(session_id)
        return crm.update(session_id, fields)

    @app.get("/api/sessions/{session_id}/events")
    async def session_events(session_id: int):
        get(session_id)
        return crm.events(session_id)

    @app.post("/api/sessions/{session_id}/events")
    async def add_event(session_id: int, event: EventIn):
        get(session_id)
        log({**event.model_dump(), "session_id": session_id})
        return {"ok": True}

    @app.post("/api/sessions/{session_id}/intervene")
    async def intervene(session_id: int, body: InterveneIn):
        session = get(session_id)
        if body.action in ("pause", "resume"):
            paused = body.action == "pause"
            session = crm.update(session_id, {"paused": paused})
            log({"session_id": session_id, "kind": "intervened",
                 "text": "Paused by a person" if paused else "Resumed: the agent handles it again"})
            return session

        if not body.body.strip():
            raise HTTPException(422, "send needs a body")
        subject = _reply_subject(crm.events(session_id))
        try:
            sent = await mailbox.reply(session["customer"], subject, body.body, session["thread_id"])
        except Exception as error:  # 5U refused or no key: show it in the session, tell the UI
            log({"session_id": session_id, "kind": "error", "text": f"Manual reply not sent: {error}"})
            raise HTTPException(502, f"mail not sent: {error}")
        session = crm.update(session_id, {"needs_human": False})
        log({"session_id": session_id, "kind": "intervened", "text": "Reply sent by a person",
             "data": {"from": sent.get("from", ""), "to": session["customer"], "subject": subject, "body": body.body}})
        return session

    @app.get("/api/stream")
    async def stream():
        return StreamingResponse(hub.sse(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


def _reply_subject(events: list[dict]) -> str:
    """Re: the customer's subject, from the first incoming mail of the session."""
    for event in events:
        if event["kind"] != "mail_in":
            continue
        subject = event["data"].get("subject")
        if not subject and ": " in event["text"]:  # agent text "RFQ from <sender>: <subject>"
            subject = event["text"].split(": ", 1)[1]
        if subject:
            return subject if subject.lower().startswith("re:") else f"Re: {subject}"
    return "Re: Your air freight request"


app = create_app()
