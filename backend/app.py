"""Backend API: CRM sessions, events, intervene and the live SSE stream. Contract: docs/CONTRACT.md.

Run: `uv run uvicorn app:app --timeout-graceful-shutdown 1 --port 8000` (from backend/), or `make backend` from the repo root.
"""

import asyncio
import base64
import hmac
import json
import os
import re
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from booking import BookingError, PriceChanged, book
from crm import Crm, now
from ingest import parse_tariff
from mailbox import FiveUMailbox
from portal import Portal
from portal_memory import PortalMemory
import portal_paste
from pricing import Pricer, chargeable_kg, weights
from stream import Broadcaster
from tariffs import DATA, Tariffs, Zones

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "crm.sqlite3"))
INGEST_DIR = Path(os.environ.get("INGEST_DIR", str(DATA / "ingested")))  # tariffs from mail, loaded at start
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
PORTAL_PASTE_SECRET = os.environ.get("PORTAL_PASTE_SECRET", "")  # POST /api/sessions/{id}/portal-rate; empty = off
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")  # needs_human / error events → https://ntfy.sh/<topic> (phone push)
# fallback quote: an earlier trucker bid for the same zone is reused only within ±25 % of this shipment's chargeable kg
PICKUP_REUSE_TOLERANCE = float(os.environ.get("PICKUP_REUSE_TOLERANCE", "0.25"))


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
    fallback: bool = False  # no trucker answered: use the earlier trucker bids for the same pickup zone


class BookIn(BaseModel):
    session_id: int
    rate_id: str | None = None


class AttachmentIn(BaseModel):
    filename: str
    content_base64: str
    password_hints: list[str] = []  # passwords named in the mail body, tried on an encrypted zip / PDF


class TariffIn(BaseModel):
    filename: str
    content_base64: str
    sender: str | None = Field("", alias="from")


# What the agent's DG / packing-list checks look for: kept even past the cap (a zip or a forwarded mail with several
# documents easily passes 20,000 characters, and the packing list is often the last file in it).
SIGNAL = re.compile(r"\bUN\s?-?\d{4}\b|\bclass\s*[1-9]\b|klasse\s*[1-9]|dangerous|gefahr|hazard|lithium|\bDG\b|"
                    r"\bmsds\b|\bsds\b|\d\s*kg\b|gross|brutto|total|gesamt|pallet|palette|\bcbm\b|m3|m³", re.I)
TEXT_CAP, SIGNAL_CAP = 20000, 10000


def capped(lines: list[str]) -> str:
    """The first TEXT_CAP characters, plus (when longer) every later line with a DG/weight signal, up to SIGNAL_CAP."""
    text = "\n".join(lines)
    if len(text) <= TEXT_CAP:
        return text
    head, rest = text[:TEXT_CAP], text[TEXT_CAP:].split("\n")[1:]  # the cut line is in head already
    signals = "\n".join(line for line in rest if SIGNAL.search(line))[:SIGNAL_CAP]
    return f"{head}\n[…]\n{signals}" if signals else head


def create_app(crm: Crm | None = None, mailbox: FiveUMailbox | None = None, pricer: Pricer | None = None,
               ingest_dir: Path = INGEST_DIR) -> FastAPI:
    crm = crm or Crm(DB_PATH)
    mailbox = mailbox or FiveUMailbox()
    pricer = pricer or Pricer(Tariffs.from_files(DATA / "tariffs.json", *sorted(ingest_dir.glob("*.json"))),
                              Zones(), Portal())
    if getattr(pricer, "memory", None) is None:
        pricer.memory = PortalMemory(crm, lambda rfq: pricer.lane(rfq, [])[:2])
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
        session = get(session_id)
        if isinstance(fields.get("bids"), list):  # a portal rate pasted meanwhile is never overwritten by the agent
            fields["bids"] += [b for b in session.get("bids") or [] if isinstance(b, dict) and b.get("manual_portal")
                               and b not in fields["bids"]]
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

    @app.post("/api/sessions/{session_id}/portal-rate")
    async def portal_rate(session_id: int, body: dict = Body(...), x_paste_secret: str = Header("")):
        """A rate a person got from the portal's web form: {"airline": "GN", "origin": "FRA", "destination": "LAX",
        "text": "<the 'Your rate' block>"}, header X-Paste-Secret = PORTAL_PASTE_SECRET. The backend is reachable
        without auth through the public Next proxy: no secret configured = this endpoint is off."""
        if not PORTAL_PASTE_SECRET or not hmac.compare_digest(x_paste_secret.encode(), PORTAL_PASTE_SECRET.encode()):
            print(f"portal-rate #{session_id}: refused, wrong or missing X-Paste-Secret")
            raise HTTPException(403, "portal paste refused")
        session = get(session_id)
        airline = str(body.get("airline") or "")
        try:
            bid = portal_paste.checked(session, airline, body.get("origin"), body.get("destination"),
                                       str(body.get("text") or ""))
        except ValueError as error:
            log({"session_id": session_id, "kind": "bid", "text": f"Portal rate paste refused ({airline[:20] or '?'}): {error}"})
            raise HTTPException(422, str(error))
        bids = session.get("bids") or []
        new = not any(isinstance(b, dict) and b.get("manual_portal") and b.get("carrier") == bid["carrier"]
                      and b.get("total") == bid["total"] for b in bids)
        if new:
            crm.update(session_id, {"bids": [*bids, bid]})
        log({"session_id": session_id, "kind": "bid", "text": f"Portal rate pasted by a person{'' if new else ' (again)'}: "
             f"{bid['carrier']} {bid['currency']} {bid['total']:,.2f}" + (f", {bid['transit_days']:g} days"
             if bid["transit_days"] else "") + (f", {bid['rate_id']}" if bid["rate_id"] else ""), "data": bid})
        return bid

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
        quote = None
        if not (session.get("quote") or session.get("booking")):
            priced = next((e["data"] for e in reversed(crm.events(session_id))
                           if e["kind"] == "priced" and isinstance(e.get("data"), dict)), {})
            quote = manual_quote(body.body, priced.get("options") or [])
            if quote and not quote.get("rate_id") and isinstance(session.get("rfq"), dict):
                try:  # handed over before pricing: price now and match the written amount against those options
                    quote = manual_quote(body.body, (await pricer.price(session["rfq"], session.get("bids") or [])
                                                     ).get("options") or [])
                except Exception as error:
                    print(f"manual quote: pricing failed, kept without a rate ID: {error}")
        if quote:  # the person's reply is our quote: the customer's "yes" is booked by the agent (+10 tracking later)
            session = crm.update(session_id, {"stage": "quoted", "quote": quote, "paused": False})
            log({"session_id": session_id, "kind": "quote_sent", "data": {"option": quote},
                 "text": f"Quote sent by a person: {quote['currency']} {quote['total']:,.2f} all-in"})
        return session

    @app.post("/api/price")
    async def price(body: PriceIn):
        bids = list(body.bids)
        if body.fallback and body.rfq.get("pickup") and not any(b.get("leg") == "pickup" for b in bids):
            bids += _earlier_pickup_bids(body.rfq)
        return await pricer.price(body.rfq, bids)

    def _earlier_pickup_bids(rfq: dict) -> list[dict]:
        """Trucker bids from earlier sessions with the same pickup zone (newest first, one per trucker)."""
        zone = pricer.zones.resolve(rfq.get("pickup"))
        if not zone:
            return []
        found: dict[str, dict] = {}
        kg = chargeable_kg(*weights(rfq))
        for s in crm.sessions():
            other = s.get("rfq") if isinstance(s.get("rfq"), dict) else {}
            if not other.get("pickup") or (pricer.zones.resolve(other["pickup"]) or {}).get("zone") != zone["zone"]:
                continue
            try:  # trap 7: a trucker prices by weight, so its bid for another weight is no price for this one
                if abs(chargeable_kg(*weights(other)) - kg) > PICKUP_REUSE_TOLERANCE * kg:
                    continue
            except (TypeError, ValueError):
                continue
            for b in s.get("bids") or []:
                if isinstance(b, dict) and b.get("leg") == "pickup" and b.get("carrier") and b["carrier"] not in found:
                    found[b["carrier"]] = {**b, "rate_id": None, "carrier": b["carrier"]}
        return list(found.values())

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
            except PriceChanged as change:  # not booked: the agent asks the customer again with the new total
                latest = get(body.session_id).get("booking") or {}
                crm.update(body.session_id, {"booking": {**latest, "pending_rate_id": change.detail["rate_id"],
                                                         "price_changed": change.detail}})
                log({"session_id": body.session_id, "kind": "priced", "text": f"Not booked: {change}",
                     "data": change.detail})
                raise HTTPException(409, change.detail)
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
            lines = extract_lines(body.filename, base64.b64decode(body.content_base64),
                                  passwords=body.password_hints[:10])
        except Exception as error:  # an image or an unknown file: nothing to read
            return {"text": "", "error": str(error)}
        return {"text": capped(lines)}

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


_NUM = r"\d{1,3}(?:[.,  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
AMOUNT = re.compile(rf"(?:(EUR|USD|€|\$)\s?({_NUM}))|(?:({_NUM})\s?(EUR|USD|€))", re.I)
SYMBOL = {"€": "EUR", "$": "USD"}


def _money(text: str) -> float:
    """"1,856.00" · "1.856,00" · "1 856" · "1856.5" → float."""
    text = re.sub(r"[  ]", "", text)
    decimal = re.search(r"[.,](\d{1,2})$", text)
    whole = re.sub(r"[.,]", "", text[: decimal.start()] if decimal else text)
    return float(f"{whole}.{decimal.group(1)}" if decimal else whole)


def manual_quote(body: str, options: list[dict]) -> dict | None:
    """The quote a person's reply states: exactly one amount (any number of mentions). It takes the option with that
    total (so the booking uses its rate ID), else a manual option without one. None when the reply states no amount
    or several different ones ("let me check and come back to you"): then it stays a plain reply, a person handles
    the answer, and a customer's "ok" can never book a shipment nobody quoted."""
    found = _amounts(body)
    if len(found) != 1:  # a breakdown ("pickup EUR 417.85 + air EUR 4,638.85"): the one "Total:" line is the price
        found = {a for line in body.splitlines() if TOTAL_LINE.match(line) for a in _amounts(line)}
    if len(found) != 1:
        return None
    [(currency, total)] = found
    option = next((o for o in options if o.get("currency") == currency
                   and abs(float(o.get("total") or 0) - total) <= 0.005 * total), None)
    own = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith(">")).lower()
    mentioned = {n for n in AIRLINES | {o.get("carrier") or "" for o in options} if n and n.lower() in own}
    if option is None and len(mentioned) == 1:  # the reply names exactly one airline: book that airline's rate
        # booked as is while the rate is valid (no fresh-rate check), so at most +5 % over the written price
        named = [o for o in options if o.get("carrier") in mentioned and o.get("currency") == currency
                 and 0.85 * total <= float(o.get("total") or 0) <= 1.05 * total]
        if named:
            option = {k: v for k, v in min(named, key=lambda o: abs(float(o["total"]) - total)).items()
                      if k in BOOKING_FIELDS}
    base = option or {"source": "manual", "carrier": None, "rate_id": None, "transit_days": None}
    return {**base, "currency": currency, "total": total, "sent_at": now(), "by": "person"}


AIRLINES = {line.split(",")[0] for line in (DATA / "start-kit" / "carrier-list.csv").read_text().splitlines()
            if line.split(",")[1:2] == ["airline"]}
TOTAL_LINE = re.compile(r"^[^\w>]*(total|gesamt\w*|all[- ]in( price)?)\b", re.I)
# what a booking needs from a priced option (the written total stays the person's)
BOOKING_FIELDS = ("source", "leg", "carrier", "airline_code", "rate_id", "transit_days", "valid_until",
                  "chargeable_weight_kg", "billed_weight_kg", "pickup")


def _amounts(text: str) -> set[tuple[str, float]]:
    return {(SYMBOL.get(m[0] or m[3], (m[0] or m[3]).upper()), _money(m[1] or m[2])) for m in AMOUNT.findall(text)}


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
