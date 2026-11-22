"""Trap suite: every rejected live round and every trap we expect next runs through the whole RFQ pipeline
(extraction mocked, nothing sent for real) and must end the way a careful forwarder ends it.

A new reject → add its mail (and attachment) to evals/traps.json with the behaviour 5U wanted, then fix until green.
"""

import json
import re
from pathlib import Path

import pytest

import amendments
import booking_agent
import extract as extract_mod
import gate
import rfq_agent
from inbox import FixtureMailbox
from test_rfq_agent import FakeApi

CASES = json.loads((Path(__file__).parent / "evals" / "traps.json").read_text())
BASE_RAW = {
    "origin": "FRA", "destination": "GRU", "ask": "cheapest", "pickup_address": None, "ready_date": "2026-11-25",
    "pieces": [{"count": 3, "length": None, "width": None, "height": None, "weight": 715, "weight_is_total": True,
                "volume": None, "volume_is_total": True}],
    "dim_unit": "cm", "weight_unit": "kg", "volume_unit": "m3", "volume": 2.65, "commodity": "machine parts",
    "dangerous_goods": False, "customer_reference": None, "language": "en",
}


class GateApi(FakeApi):
    """FakeApi that records texts and can say a person paused the session."""

    def __init__(self, price_result, paused=False):
        super().__init__(price_result)
        self.paused, self.texts, self.findings = paused, [], []

    def session(self, session_id):
        return {"paused": self.paused}

    def price(self, rfq, bids=None, fallback=False):
        """Like backend.Backend.price: the cargo insurance premium the customer asked for goes into every all-in."""
        import copy
        import insurance
        return insurance.add(copy.deepcopy(super().price(rfq, bids, fallback)), rfq)

    def attachment_text(self, filename, content_base64, password_hints=()):
        """The backend's real reader (documents, archives in memory), like /api/attachments/text."""
        import base64
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
        from ingest import extract_lines
        try:
            return "\n".join(extract_lines(filename, base64.b64decode(content_base64), passwords=password_hints))
        except Exception:
            return ""

    def event(self, session_id, kind, text, data=None, cost=0.0):
        super().event(session_id, kind, text, data, cost)
        self.texts.append(text)
        if text.startswith("Quote gate:"):
            self.findings += (data or {}).get("findings", [])


def run(case, tmp_path, monkeypatch, paused=False):
    raw = {**BASE_RAW, **case.get("raw", {})}
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    monkeypatch.setattr(rfq_agent, "GATE_AUTO_SEND_SECONDS", 0.0)  # the dead man's switch fires at once
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: None)
    options = case["options"]
    api = GateApi({"options": options, "chosen": options[case["chosen"]], "why": "test",
                   "warnings": case.get("warnings", [])}, paused)
    box = FixtureMailbox(tmp_path)
    mail = {"id": "m1", "thread_id": f"t-{case['name'][:10]}", "from": "buyer@customer.example",
            "subject": "Air freight quote", "body": case["body"], "attachments": case.get("attachments", [])}
    rfq_agent.handle_rfq(mail, box, api)
    return box, api, {f["code"] for f in api.findings}


@pytest.mark.parametrize("case", [pytest.param(c, marks=pytest.mark.xfail(reason=c["known_issue"]))
                                  if c.get("known_issue") else c for c in CASES], ids=[c["name"] for c in CASES])
def test_trap(case, tmp_path, monkeypatch):
    box, api, codes = run(case, tmp_path, monkeypatch)
    expect = case["expect"]
    assert len(box.sent) == (1 if expect.get("sent", True) else 0), api.texts
    body = box.sent[0]["body"] if box.sent else ""
    held = any(t.startswith("Quote held") for t in api.texts)
    if "hold" in expect:
        assert held == expect["hold"], api.texts
    assert set(expect.get("codes", [])) <= codes, (codes, api.texts)
    assert not set(expect.get("codes_absent", [])) & codes, codes
    for text in expect.get("contains", []):
        assert text in body
    for text in expect.get("lacks", []):
        assert text not in body
    if expect.get("sent") is False:  # nothing went out (spam, or handed to a person): no quote at all
        assert "quote_sent" not in api.events
        if expect.get("person") is not None:
            assert ("needs_human" in api.events) == expect["person"], api.texts
        return
    if expect.get("question"):  # we asked first: no quote, no amount in the mail
        assert "quote_sent" not in api.events and not re.findall(r"\d[\d,.]*\.\d{2}", body), body
        return
    if "carrier" in expect:
        assert api.data["quote_sent"]["option"]["carrier"] == expect["carrier"]
    amount = expect.get("amount") or f"{api.data['quote_sent']['option']['total']:,.2f}"
    assert re.findall(r"\d[\d,.]*\.\d{2}", body) == [amount]  # every quote states exactly one amount


def test_a_held_quote_is_not_sent_when_a_person_pauses(tmp_path, monkeypatch):
    case = next(c for c in CASES if "USD" in c["name"])
    box, api, codes = run(case, tmp_path, monkeypatch, paused=True)
    assert box.sent == [] and "currency" in codes and "needs_human" in api.events


def test_warn_mode_logs_but_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "MODE", "warn")
    case = next(c for c in CASES if c["name"].startswith("cheapest, but it must arrive"))
    box, api, codes = run(case, tmp_path, monkeypatch)
    assert api.data["quote_sent"]["option"]["carrier"] == "Kestrel Airways" and "deadline" in codes


def test_a_gate_crash_never_costs_the_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "review", lambda *a, **k: 1 / 0)
    box, api, _ = run(CASES[2], tmp_path, monkeypatch)
    assert len(box.sent) == 1 and any("Quote gate skipped" in t for t in api.texts)


def test_a_correction_before_the_quote_is_read_with_the_request(tmp_path, monkeypatch):
    reads = []

    def fake_extract(mail, model=None):
        reads.append(mail["body"])
        weight = 850 if "Correction" in mail["body"] else 715
        return {**BASE_RAW, "pieces": [{**BASE_RAW["pieces"][0], "weight": weight}]}, 0.0001

    monkeypatch.setattr(extract_mod, "extract", fake_extract)
    session = {"id": 1, "thread_id": "t-corr", "stage": "pricing"}
    correction = {"id": "m2", "thread_id": "t-corr", "from": "buyer@customer.example", "subject": "Re: quote",
                  "body": "Correction: the gross weight is 850 kg, not 715 kg.", "attachments": []}
    booking_agent.handle_customer_reply(correction, FixtureMailbox(tmp_path), GateApi({}), session)
    option = CASES[2]["options"][0]
    api, box = GateApi({"options": [option], "chosen": option, "why": "test"}), FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq({"id": "m1", "thread_id": "t-corr", "from": "buyer@customer.example", "subject": "quote",
                          "body": "3 pieces, 715 kg, 2.65 cbm.", "attachments": []}, box, api)
    assert len(reads) == 2 and reads[1].startswith("Correction")
    assert round(sum(p["count"] * p["weight_kg"] for p in api.data["extracted"]["pieces"])) == 850
    assert len(box.sent) == 1 and amendments.take("t-corr") == []


def test_a_yes_with_a_change_is_not_a_plain_yes(monkeypatch):
    asked = []
    monkeypatch.setattr(booking_agent.llm, "chat_json",
                        lambda *a, **k: (asked.append(a) or {"intent": "question"}, 0.00001))
    assert booking_agent.read_intent("OK, book it, but please change the pickup to the 30th.")[0] == "question"
    assert asked  # the rules didn't book it
    assert booking_agent.read_intent("That works for us, please go ahead and book it.") == ("accept", 0.0)
