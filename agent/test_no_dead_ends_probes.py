"""Regression probes from the #80 review: each test reproduces a former bug and PASSES only if that bug is back.
Strict xfail: today they fail (bug gone), and a returning bug turns the suite red."""
import pytest

pytestmark = pytest.mark.xfail(strict=True, reason="probe passes only if the #80 bug is back")

import rfq_agent, main
from bids import BidBoard
from inbox import FixtureMailbox
from test_rfq_agent import FakeApi, MAIL, OPTION, RAW, to_rfq


def _read_as(missing):
    return lambda mail: {"rfq": to_rfq(RAW)[0], "missing": missing, "cost": 0.0001, "model": "m", "escalated": None}


def test_fallback_store_hiccup_sends_two(tmp_path, monkeypatch):
    """no chosen price -> fallback quote sent, storing it fails -> except runs the fallback AGAIN."""
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(rfq_agent, "read_request", _read_as([]))

    class StoreFailsOnce(FakeApi):
        failed = False

        def update(self, sid, **f):
            if "quote" in f and not StoreFailsOnce.failed:
                StoreFailsOnce.failed = True
                raise RuntimeError("502")
            super().update(sid, **f)

    api = StoreFailsOnce({"options": [], "chosen": None})
    api.fallback_result = {"options": [OPTION], "chosen": OPTION, "why": "fb"}
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert len(box.sent) == 2


def test_crash_before_missing_check_quotes_unchecked_reading(tmp_path, monkeypatch):
    """origin missing + odd density, api.event('extracted') blips -> the except sends a fallback anyway."""
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(rfq_agent, "read_request", _read_as(["origin", "implausible density: 5 kg in 30 m3"]))

    class Blip(FakeApi):
        def event(self, sid, kind, text, data=None, cost=0.0):
            if kind == "extracted":
                raise RuntimeError("backend restarting")
            super().event(sid, kind, text, data, cost)

        def session(self, sid):  # the except's update(needs_human=True) reached the real backend
            return {"paused": False, "needs_human": True, "quote": None}

    api = Blip({"options": [OPTION], "chosen": OPTION})
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert len(box.sent) == 1 and api.fallback


def test_restart_after_quote_store_failed_quotes_again(tmp_path, monkeypatch):
    """quote sent, storing it failed -> except marks failed+needs_human -> restart -> resume picks the fallback."""
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(rfq_agent, "read_request", _read_as([]))

    class StoreFails(FakeApi):
        def update(self, sid, **f):
            if "quote" in f:
                raise RuntimeError("502")
            super().update(sid, **f)

    box = FixtureMailbox(tmp_path)
    api = StoreFails({"options": [OPTION], "chosen": OPTION})
    rfq_agent.handle_rfq(MAIL, box, api, BidBoard(), [], cutoff_s=0)
    assert len(box.sent) == 1
    stored = {}
    for u in api.updates:
        stored.update(u)
    assert stored["stage"] == "failed" and stored["needs_human"] is True and not stored.get("quote")
    session = {"id": 1, "thread_id": "t1", "bids": [], **stored, "received_at": None}
    started = []
    monkeypatch.setattr(main, "_start", lambda h, *a: started.append(h.__name__))
    monkeypatch.setattr(box, "get", lambda tid: {**MAIL, "received_at": None}, raising=False)

    class Api2(FakeApi):
        def sessions(self):
            return [session]

    main.resume_unfinished(box, Api2({}), BidBoard(), [])
    assert started == ["fallback_after_restart"]
    api3 = FakeApi({"options": [OPTION], "chosen": OPTION})
    api3.events.append("needs_human")
    rfq_agent.fallback_after_restart(session, {**MAIL, "received_at": None}, box, api3)
    assert len(box.sent) == 2  # second quote in the same thread


def test_restart_quotes_a_missing_weight_handover(tmp_path, monkeypatch):
    """'missing: weight' never got a fallback before a restart; after it, fallback_after_restart prices it."""
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    rfq = to_rfq({**RAW, "pieces": [{**RAW["pieces"][0], "weight": None}]})[0]
    api = FakeApi({"options": [OPTION], "chosen": OPTION})
    api.events.append("needs_human")
    box = FixtureMailbox(tmp_path)
    rfq_agent.fallback_after_restart({"id": 1, "rfq": rfq, "bids": []}, {**MAIL, "received_at": None}, box, api)
    assert len(box.sent) == 1 and api.fallback


def test_packing_list_weight_skips_the_density_check(tmp_path, monkeypatch):
    """mail: no weight, 0.05 m3; packing list: 7150 kg (143,000 kg/m3) -> priced at once, nobody asked to check."""
    rfq = to_rfq({**RAW, "volume": 0.05, "pieces": [{**RAW["pieces"][0], "weight": None, "length": None,
                                                    "width": None, "height": None}]})[0]
    monkeypatch.setattr(rfq_agent, "read_request",
                        lambda mail: {"rfq": rfq, "missing": ["weight"], "cost": 0.0, "model": "m", "escalated": None})
    monkeypatch.setattr(rfq_agent, "_attachment_texts", lambda *a: ["Total gross weight (kg): 7150"])
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: None)
    api = FakeApi({"options": [OPTION], "chosen": OPTION})
    box = FixtureMailbox(tmp_path)
    rfq_agent.handle_rfq({**MAIL, "received_at": None}, box, api, BidBoard(), [], cutoff_s=0)
    assert len(box.sent) == 1 and "needs_human" not in api.events
