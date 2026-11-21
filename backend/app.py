"""Backend API: CRM sessions, events, intervene and the live SSE stream. Contract: docs/CONTRACT.md.

Run: `uv run uvicorn app:app --timeout-graceful-shutdown 1 --port 8000` (from backend/), or `make backend` from the repo root.
"""

import asyncio
import base64
import json
import os
import re
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from booking import BookingError, book
from crm import Crm
from ingest import parse_tariff
from mailbox import FiveUMailbox
from portal import Portal
from pricing import Pricer
from stream import Broadcaster
from tariffs import DATA, Tariffs, Zones

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "crm.sqlite3"))
INGEST_DIR = Path(os.environ.get("INGEST_DIR", str(DATA / "ingested")))  # tariffs from mail, loaded at start
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")  # needs_human / error events → https://ntfy.sh/<topic> (phone push)


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


class PriceIn(BaseModel):
    rfq: dict
    bids: list[dict] = []


class BookIn(BaseModel):
    session_id: int
    rate_id: str | None = None


class AttachmentIn(BaseModel):
    filename: str
    content_base64: str


class TariffIn(BaseModel):
    filename: str
    content_base64: str
    sender: str | None = Field("", alias="from")


def create_app(crm: Crm | None = None, mailbox: FiveUMailbox | None = None, pricer: Pricer | None = None,
               ingest_dir: Path = INGEST_DIR) -> FastAPI:
    crm = crm or Crm(DB_PATH)
    mailbox = mailbox or FiveUMailbox()
    pricer = pricer or Pricer(Tariffs.from_files(DATA / "tariffs.json", *sorted(ingest_dir.glob("*.json"))),
                              Zones(), Portal())
    hub = Broadcaster()
    background: set[asyncio.Task] = set()
    app = FastAPI(title="leylu forwarder backend")
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
    app.state.crm, app.state.hub, app.state.pricer = crm, hub, pricer

    def get(session_id: int) -> dict:
        session = crm.session(session_id)
        if session is None:
            raise HTTPException(404, f"no session {session_id}")
        return session

    def log(event: dict) -> dict:
        stored = crm.add_event(event)
        hub.publish(stored)
        if NTFY_TOPIC and stored["kind"] in ("needs_human", "error"):
            task = asyncio.ensure_future(_push(stored))
            background.add(task)
            task.add_done_callback(background.discard)
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
        if isinstance(fields.get("rfq"), dict):  # portal lookups run during the bid round, not at the cut-off
            task = asyncio.create_task(pricer.prefetch(fields["rfq"]))
            background.add(task)
            task.add_done_callback(background.discard)
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
        crm.update(session_id, {"paused": True})  # the agent checks paused before every send
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

    @app.post("/api/price")
    async def price(body: PriceIn):
        return await pricer.price(body.rfq, body.bids)

    booking_locks: dict[int, asyncio.Lock] = {}

    @app.post("/api/book")
    async def book_rate(body: BookIn):
        """One booking per session: a second call (two "yes" mails, a retry) returns the first booking."""
        get(body.session_id)
        async with booking_locks.setdefault(body.session_id, asyncio.Lock()):
            session = get(body.session_id)
            if (session.get("booking") or {}).get("booking_reference"):
                return session["booking"]
            try:
                booking, note = await book(pricer, session, body.rate_id, remember=lambda rate_id: crm.update(
                    body.session_id, {"booking": {**(session.get("booking") or {}), "pending_rate_id": rate_id}}))
            except (BookingError, httpx.HTTPError) as error:
                text = str(error) if isinstance(error, BookingError) else f"portal unreachable: {error}"
                log({"session_id": body.session_id, "kind": "error", "text": f"Booking failed: {text}"})
                raise HTTPException(502, text)
            crm.update(body.session_id, {"booking": booking})
            if note:
                log({"session_id": body.session_id, "kind": "priced", "text": note, "data": booking})
            return booking

    @app.post("/api/attachments/text")
    def attachment_text(body: AttachmentIn):  # sync: FastAPI runs the PDF parsing in a thread, not on the event loop
        """The text of an RFQ attachment (packing list, SLI as xlsx/pdf/docx/txt/csv) for the agent's trap checks."""
        try:
            from ingest import extract_lines
            lines = extract_lines(body.filename, base64.b64decode(body.content_base64))
        except Exception as error:  # an image or an unknown file: nothing to read
            return {"text": "", "error": str(error)}
        return {"text": "\n".join(lines)[:20000]}

    @app.post("/api/tariffs/ingest")
    async def ingest_tariff(body: TariffIn):
        """An airline's tariff from mail → the tariffs used for pricing (and saved, so a restart keeps it)."""
        try:
            sheet = parse_tariff(body.filename, base64.b64decode(body.content_base64))
        except Exception as error:  # unknown layout, image, broken file: a person enters it
            log({"session_id": None, "kind": "tariff_ingested", "llm_cost_usd": 0,
                 "text": f"Tariff {body.filename} from {body.sender} NOT read: {error}",
                 "data": {"filename": body.filename, "from": body.sender, "error": str(error)}})
            return {"rows": 0, "error": str(error)}
        rows = pricer.tariffs.add(sheet)
        ingest_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", sheet["airline"].lower()).strip("-")
        target = ingest_dir / f"{slug}-{sheet['valid_from']}.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps({"sheets": [sheet]}, indent=1))
        os.replace(temp, target)  # a restart mid-write never leaves a half file
        log({"session_id": None, "kind": "tariff_ingested", "llm_cost_usd": 0,
             "text": f"Tariff {sheet['airline']}: {rows} lanes, valid {sheet['valid_from']} to {sheet['valid_to']}",
             "data": {"filename": body.filename, "from": body.sender, "airline": sheet["airline"], "rows": rows,
                      "valid_from": sheet["valid_from"], "valid_to": sheet["valid_to"]}})
        return {"rows": rows, "airline": sheet["airline"], "valid_until": sheet["valid_to"]}

    @app.get("/api/stream")
    async def stream():
        return StreamingResponse(hub.sse(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


async def _push(event: dict) -> None:
    """Phone push for a session that needs a person (ntfy.sh). Never raises: the API must not wait on it."""
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            await http.post(f"https://ntfy.sh/{NTFY_TOPIC}", content=f"#{event['session_id']}: {event['text']}"[:300],
                            headers={"Title": f"Leylu: {event['kind']}", "Priority": "high"})
    except Exception as error:
        print(f"ntfy push failed: {error}")


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
