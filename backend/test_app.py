import asyncio
import base64
from pathlib import Path

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


def test_attachment_text_reads_the_real_round_10_xlsx_and_round_11_pdf():
    fixtures = Path(__file__).parent / "fixtures"
    c = client()
    for name, un in (("round10_PL_53839.xlsx", "UN1133"), ("round11_packing-spec_33955.pdf", "UN1950")):
        content = base64.b64encode((fixtures / name).read_bytes()).decode()
        text = c.post("/api/attachments/text", json={"filename": name, "content_base64": content}).json()["text"]
        assert un in text and "Total gross weight" in text, name
    broken = c.post("/api/attachments/text", json={"filename": "x.pdf", "content_base64": "bm90IGEgcGRm"}).json()
    assert broken["text"] == ""  # an unreadable file never fails the request


def test_a_manual_reply_with_one_price_becomes_the_quote_so_a_yes_gets_booked():
    from app import manual_quote
    box = FakeMailbox()
    c = client(box)
    sid = c.post("/api/sessions", json={"customer": "buyer@acme.example", "thread_id": 77}).json()["id"]
    option = {"source": "portal", "carrier": "SkyAir", "rate_id": "R-abc123", "currency": "EUR", "total": 1856.0}
    c.post(f"/api/sessions/{sid}/events", json={"kind": "priced", "text": "1 option", "data": {"options": [option]}})
    c.patch(f"/api/sessions/{sid}", json={"needs_human": True})
    body = "Hi Anna,\n\nwe can fly it with SkyAir. All-in price: EUR 1,856.00\n\nBest regards"
    s = c.post(f"/api/sessions/{sid}/intervene", json={"action": "send", "body": body}).json()
    assert s["stage"] == "quoted" and s["paused"] is False and s["needs_human"] is False
    assert s["quote"]["rate_id"] == "R-abc123" and s["quote"]["total"] == 1856.0 and s["quote"]["by"] == "person"
    assert c.get(f"/api/sessions/{sid}/events").json()[-1]["kind"] == "quote_sent"
    # a second manual mail never replaces the first quote (only the first one counts)
    assert c.post(f"/api/sessions/{sid}/intervene", json={"action": "send", "body": "EUR 999"}).json()["quote"]["total"] == 1856.0

    assert manual_quote("Price: 2.481,50 € all-in", [])["total"] == 2481.5  # German style, no priced option
    assert manual_quote("Air EUR 2,100 + pickup EUR 245.02", []) is None  # two amounts: a person decides
    assert manual_quote("We'll get back to you shortly.", []) is None



def test_a_manual_quote_with_a_breakdown_or_another_trucker_still_books_the_named_airline():
    """Rounds 17 and 18: the person's reply was the quote, but the 'yes' could not be booked (no rate ID)."""
    from app import manual_quote
    lumen = {"source": "portal", "leg": "air", "carrier": "Lumen Air Cargo", "airline_code": "LM", "rate_id": "R-lm1",
             "currency": "EUR", "total": 2278.18, "transit_days": 4.5, "chargeable_weight_kg": 874.0,
             "billed_weight_kg": 1000.0, "pickup": {"carrier": "Elbkante Logistik", "total": 128.18},
             "breakdown": [{"label": "x", "amount": 2150.0}]}
    other = {**lumen, "carrier": "Wayzata Air Cargo", "airline_code": "WZ", "rate_id": None, "total": 3149.58}
    # round 18: the re-price picked another trucker, so no total matches; the reply names Lumen
    quote = manual_quote("Total: EUR 2,358.88 all-in\n\n... air freight to SGN with Lumen Air Cargo ...", [other, lumen])
    assert quote["rate_id"] == "R-lm1" and quote["airline_code"] == "LM" and quote["total"] == 2358.88
    assert quote["by"] == "person" and "breakdown" not in quote
    # round 17: a breakdown under the total line
    body = ("Total: EUR 5,056.70 all-in\n- Truck pickup: EUR 417.85\n- Air freight with Nova Atlas Cargo: EUR 4,638.85")
    nova = {**lumen, "carrier": "Nova Atlas Cargo", "airline_code": "NV", "rate_id": "R-nv1", "total": 5005.60}
    assert manual_quote(body, [nova])["rate_id"] == "R-nv1"
    assert manual_quote(body, [])["total"] == 5056.70  # no options: still the quote, booked by a person
    # no airline named and no matching total: a manual quote without a rate (unchanged)
    assert manual_quote("Total: EUR 2,358.88 all-in", [other, lumen])["rate_id"] is None
    # the agent's QUOTE_STYLE=human sentence
    sentence = "The all-in price is EUR 5,056.70, including the pickup, air freight, fuel and security."
    assert manual_quote(sentence, [{**nova, "total": 5056.70}])["rate_id"] == "R-nv1"
    # a named airline far from the written price is not taken
    assert manual_quote("EUR 9,999.00 with Lumen Air Cargo", [lumen])["rate_id"] is None


def test_a_manual_quote_never_books_an_ambiguous_or_dearer_airline():
    from app import manual_quote
    lumen = {"source": "portal", "carrier": "Lumen Air Cargo", "rate_id": "R-lm1", "currency": "EUR", "total": 2278.18}
    fjord = {"source": "portal", "carrier": "Fjordline Air Cargo", "rate_id": "R-fj1", "currency": "EUR", "total": 2310.0}
    two = manual_quote("EUR 2,300.00 all-in, not Lumen Air Cargo but Fjordline Air Cargo", [lumen, fjord])
    assert two is None or two.get("rate_id") != "R-lm1"  # two airlines named: never book Lumen's rate
    dearer = manual_quote("EUR 2,000.00 all-in with Lumen Air Cargo", [lumen])  # Lumen's rate is 14 % higher
    assert dearer is None or not dearer.get("rate_id")
    pasted = manual_quote("Air EUR 2,100 + pickup EUR 245\n\n> Total budget: EUR 3,000", [])
    assert pasted is None or pasted["total"] != 3000.0  # the customer's quoted budget is never our price
