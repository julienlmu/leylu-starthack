import asyncio

from fastapi.testclient import TestClient

from app import _reply_subject, create_app
from crm import Crm
from stream import Broadcaster

RFQ = {"origin": "MUC", "destination": "JFK", "ask": "fastest", "pickup": None, "ready_date": "2026-11-23",
       "pieces": [{"count": 3, "length_cm": 120, "width_cm": 80, "height_cm": 100, "weight_kg": 140}],
       "volume_m3": None, "commodity": "machine parts", "dangerous_goods": False,
       "customer_reference": "PO-4711", "language": "de"}


class FakeMailbox:
    def __init__(self, fail: bool = False):
        self.sent, self.fail = [], fail

    async def reply(self, to, subject, body, in_reply_to):
        if self.fail:
            raise RuntimeError("422 from 5U")
        self.sent.append({"to": to, "subject": subject, "body": body, "in_reply_to": in_reply_to})
        return {"id": 99, "from": "leylu@hackloop.mail"}


def client(mailbox=None) -> TestClient:
    return TestClient(create_app(Crm(":memory:"), mailbox or FakeMailbox()))


def test_health():
    assert client().get("/health").json() == {"ok": True}


def test_session_lifecycle_like_the_agent():
    c = client()
    sid = c.post("/api/sessions", json={"customer": "buyer@acme.example", "thread_id": 1042}).json()["id"]
    s = c.get(f"/api/sessions/{sid}").json()
    assert s["stage"] == "new" and s["outcome"] == "open" and s["bids"] == [] and s["rfq"] is None
    assert s["thread_id"] == 1042  # 5U ids stay integers, so the agent can reply with them
    assert s["paused"] is False and s["needs_human"] is False and s["llm_cost_usd"] == 0

    c.patch(f"/api/sessions/{sid}", json={"stage": "pricing", "rfq": RFQ, "llm_cost_usd": 0.000133})
    quote = {"source": "portal", "carrier": "Kestrel Airways", "rate_id": "R-abc12345", "currency": "EUR",
             "total": 1856.0, "transit_days": 1, "sent_at": "2026-11-21T16:01:32+00:00"}
    s = c.patch(f"/api/sessions/{sid}", json={"stage": "quoted", "quote": quote, "unknown": 1}).json()
    assert s["stage"] == "quoted" and s["quote"]["rate_id"] == "R-abc12345" and s["rfq"]["origin"] == "MUC"
    assert s["llm_cost_usd"] == 0.000133

    booking = {"booking_reference": "BK-1A2B3C4D", "rate_id": "R-abc12345", "airline": "Kestrel Airways",
               "status": "booked", "booked_at": "2026-11-21T16:09:12+00:00"}
    c.patch(f"/api/sessions/{sid}", json={"stage": "booked", "outcome": "won", "booking": booking})
    s = c.patch(f"/api/sessions/{sid}", json={"booking": {**booking, "status": "confirmed"},
                                              "status_updates": [{"at": "…", "text": "confirmed"}]}).json()
    assert s["booking"]["status"] == "confirmed" and len(s["status_updates"]) == 1 and s["outcome"] == "won"


def test_patch_with_nulls_keeps_the_session_valid():
    c = client()
    sid = c.post("/api/sessions", json={"customer": "a@x.example", "thread_id": 1}).json()["id"]
    s = c.patch(f"/api/sessions/{sid}", json={"stage": None, "bids": None, "status_updates": None, "rfq": None}).json()
    assert s["stage"] == "new" and s["bids"] == [] and s["status_updates"] == [] and s["rfq"] is None
    assert c.get("/api/sessions", params={"q": "a@x"}).status_code == 200


def test_unknown_session_is_404():
    c = client()
    assert c.get("/api/sessions/5").status_code == 404
    assert c.patch("/api/sessions/5", json={"stage": "done"}).status_code == 404
    assert c.post("/api/sessions/5/events", json={"kind": "error", "text": "x"}).status_code == 404


def test_find_by_thread_and_reference():
    c = client()
    first = c.post("/api/sessions", json={"customer": "a@x.example", "thread_id": "t-1"}).json()["id"]
    second = c.post("/api/sessions", json={"customer": "b@x.example", "thread_id": "t-2"}).json()["id"]
    c.patch(f"/api/sessions/{first}", json={"rfq": RFQ})
    c.patch(f"/api/sessions/{second}", json={"booking": {"booking_reference": "BK-1A2B3C4D", "rate_id": "R-xyz98765"}})

    assert c.get("/api/sessions/find", params={"thread_id": "t-2"}).json()["id"] == second
    assert c.get("/api/sessions/find", params={"thread_id": "nope"}).json() is None
    assert c.get("/api/sessions/find", params={"reference": "po-4711"}).json()["id"] == first
    assert c.get("/api/sessions/find", params={"reference": "bk-1a2b3c4d"}).json()["id"] == second
    assert c.get("/api/sessions/find", params={"reference": "R-xyz98765"}).json()["id"] == second
    assert c.get("/api/sessions/find", params={"reference": "BK-00000000"}).json() is None


def test_search_and_filters():
    c = client()
    a = c.post("/api/sessions", json={"customer": "buyer@acme.example", "thread_id": 1}).json()["id"]
    b = c.post("/api/sessions", json={"customer": "ops@globex.example", "thread_id": 2}).json()["id"]
    c.patch(f"/api/sessions/{a}", json={"rfq": RFQ, "stage": "quoted"})
    c.patch(f"/api/sessions/{b}", json={"needs_human": True, "stage": "failed"})

    assert [s["id"] for s in c.get("/api/sessions").json()] == [b, a]  # newest first
    assert [s["id"] for s in c.get("/api/sessions", params={"q": "jfk"}).json()] == [a]
    assert [s["id"] for s in c.get("/api/sessions", params={"q": "PO-4711"}).json()] == [a]
    assert [s["id"] for s in c.get("/api/sessions", params={"q": f"#{b}"}).json()] == [b]
    assert [s["id"] for s in c.get("/api/sessions", params={"q": "globex"}).json()] == [b]
    assert [s["id"] for s in c.get("/api/sessions", params={"stage": "quoted"}).json()] == [a]
    assert [s["id"] for s in c.get("/api/sessions", params={"needs_human": "true"}).json()] == [b]


def test_events_are_stored_in_order():
    c = client()
    sid = c.post("/api/sessions", json={"customer": "a@x.example", "thread_id": 1}).json()["id"]
    c.post(f"/api/sessions/{sid}/events", json={"session_id": sid, "at": "2026-11-21T16:00:01+00:00",
                                                 "kind": "mail_in", "text": "RFQ from a@x.example: MUC-JFK",
                                                 "data": {}, "llm_cost_usd": 0})
    c.post(f"/api/sessions/{sid}/events", json={"kind": "extracted", "text": "MUC → JFK", "data": RFQ,
                                                 "llm_cost_usd": 0.000133})
    events = c.get(f"/api/sessions/{sid}/events").json()
    assert [e["kind"] for e in events] == ["mail_in", "extracted"]
    assert events[1]["data"]["origin"] == "MUC" and events[1]["llm_cost_usd"] == 0.000133 and events[1]["at"]


def test_intervene_pause_resume_and_send():
    box = FakeMailbox()
    c = client(box)
    sid = c.post("/api/sessions", json={"customer": "buyer@acme.example", "thread_id": 1042}).json()["id"]
    c.post(f"/api/sessions/{sid}/events", json={"kind": "mail_in", "text": "RFQ from buyer@acme.example: Air MUC-JFK"})
    c.patch(f"/api/sessions/{sid}", json={"needs_human": True})

    assert c.post(f"/api/sessions/{sid}/intervene", json={"action": "pause"}).json()["paused"] is True
    assert c.post(f"/api/sessions/{sid}/intervene", json={"action": "resume"}).json()["paused"] is False
    assert c.post(f"/api/sessions/{sid}/intervene", json={"action": "send", "body": " "}).status_code == 422

    s = c.post(f"/api/sessions/{sid}/intervene", json={"action": "send", "body": "Dear Ms Weber, …"}).json()
    assert s["needs_human"] is False
    assert box.sent == [{"to": "buyer@acme.example", "subject": "Re: Air MUC-JFK", "body": "Dear Ms Weber, …",
                         "in_reply_to": 1042}]
    kinds = [e["kind"] for e in c.get(f"/api/sessions/{sid}/events").json()]
    assert kinds == ["mail_in", "intervened", "intervened", "intervened"]
    assert c.get(f"/api/sessions/{sid}/events").json()[-1]["data"]["body"] == "Dear Ms Weber, …"


def test_intervene_send_failure_is_502_and_logged():
    c = client(FakeMailbox(fail=True))
    sid = c.post("/api/sessions", json={"customer": "a@x.example", "thread_id": 7}).json()["id"]
    assert c.post(f"/api/sessions/{sid}/intervene", json={"action": "send", "body": "hi"}).status_code == 502
    assert c.get(f"/api/sessions/{sid}/events").json()[-1]["kind"] == "error"


def test_reply_subject():
    assert _reply_subject([]) == "Re: Your air freight request"
    assert _reply_subject([{"kind": "mail_in", "text": "x", "data": {"subject": "Re: Anfrage"}}]) == "Re: Anfrage"
    assert _reply_subject([{"kind": "mail_in", "text": "RFQ from a@b.c: Anfrage: MUC", "data": {}}]) == "Re: Anfrage: MUC"


def test_stream_sends_published_events_and_pings():
    async def run():
        hub = Broadcaster()
        sse = hub.sse(ping_s=0.05)
        assert await sse.__anext__() == ": connected\n\n"
        assert await sse.__anext__() == ": ping\n\n"
        hub.publish({"session_id": 1, "kind": "quote_sent"})
        assert await sse.__anext__() == 'data: {"session_id": 1, "kind": "quote_sent"}\n\n'
        await sse.aclose()
        assert not hub.queues  # a closed connection unsubscribes

    asyncio.run(run())


def test_posted_events_reach_the_stream():
    app = create_app(Crm(":memory:"), FakeMailbox())
    c = TestClient(app)
    sid = c.post("/api/sessions", json={"customer": "a@x.example", "thread_id": 1}).json()["id"]
    got = []
    app.state.hub.queues.add(q := _Collect(got))
    c.post(f"/api/sessions/{sid}/events", json={"kind": "bid", "text": "Kestrel: EUR 1,856.00"})
    app.state.hub.queues.discard(q)
    assert got and got[0]["kind"] == "bid" and got[0]["session_id"] == sid


class _Collect:
    def __init__(self, sink: list):
        self.sink = sink

    def put_nowait(self, item):
        self.sink.append(item)


def test_find_by_our_team_reference():
    c = client()
    sid = c.post("/api/sessions", json={"customer": "a@x.example", "thread_id": 9}).json()["id"]
    assert c.get("/api/sessions/find", params={"reference": f"S-{sid}"}).json()["id"] == sid
    assert c.get("/api/sessions/find", params={"reference": "S-999"}).json() is None
