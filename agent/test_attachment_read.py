import rfq_agent

MAIL = {"id": 1, "subject": "RFQ", "body": "Please find our request attached.", "received_at": "2026-11-21T19:00:00+00:00"}
SHEET = "Origin,FRA\nDestination,GRU\nGross weight (kg),715\nVolume (cbm),2.65"


class Events:
    def __init__(self):
        self.texts = []

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.texts.append(text)


def _first(missing):
    return {"rfq": {"origin": None}, "missing": missing, "cost": 0.0001, "model": "luna", "escalated": None}


def test_the_attachment_is_read_when_the_mail_leaves_the_route_and_weight_open(monkeypatch):
    seen = []

    def read(mail):
        seen.append(mail["body"])
        return {**_first([]), "rfq": {"origin": "FRA"}, "cost": 0.0002}

    monkeypatch.setattr(rfq_agent, "read_request", read)
    api = Events()
    got = rfq_agent._read_attachments_too(1, MAIL, _first(["origin", "destination", "weight"]), [SHEET], api)
    assert got["rfq"]["origin"] == "FRA" and got["missing"] == [] and round(got["cost"], 6) == 0.0003
    assert "715" in seen[0] and seen[0].startswith(MAIL["body"])  # the mail first, the attachment below it
    assert any("read again with the attachment" in t for t in api.texts)


def test_no_second_read_when_nothing_is_missing_or_no_attachment_or_switched_off(monkeypatch):
    monkeypatch.setattr(rfq_agent, "read_request", lambda mail: (_ for _ in ()).throw(AssertionError("no 2nd call")))
    first = _first([])
    assert rfq_agent._read_attachments_too(1, MAIL, first, [SHEET], Events()) is first
    first = _first(["dimensions or volume"])  # priced on the weight anyway: not worth a call
    assert rfq_agent._read_attachments_too(1, MAIL, first, [SHEET], Events()) is first
    first = _first(["weight"])
    assert rfq_agent._read_attachments_too(1, MAIL, first, [], Events()) is first
    monkeypatch.setattr(rfq_agent, "ATTACHMENT_READ", False)
    assert rfq_agent._read_attachments_too(1, MAIL, first, [SHEET], Events()) is first


def test_a_second_read_that_is_not_better_keeps_the_first_and_a_failing_one_costs_nothing(monkeypatch):
    monkeypatch.setattr(rfq_agent, "read_request", lambda mail: _first(["weight"]))
    first = _first(["weight"])
    got = rfq_agent._read_attachments_too(1, MAIL, first, [SHEET], Events())
    assert got["missing"] == ["weight"] and round(got["cost"], 6) == 0.0002  # both calls are paid for
    monkeypatch.setattr(rfq_agent, "read_request", lambda mail: (_ for _ in ()).throw(TimeoutError()))
    assert rfq_agent._read_attachments_too(1, MAIL, first, [SHEET], Events()) is first


def test_a_long_attachment_is_cut(monkeypatch):
    seen = []
    monkeypatch.setattr(rfq_agent, "read_request", lambda mail: seen.append(mail["body"]) or _first(["weight"]))
    rfq_agent._read_attachments_too(1, MAIL, _first(["weight"]), ["x" * 10000] * 5, Events())
    assert len(seen[0]) < len(MAIL["body"]) + 3 * (rfq_agent.ATTACHMENT_CHARS + 40)
