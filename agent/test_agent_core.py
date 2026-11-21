import json
from types import SimpleNamespace

import pytest

import llm
from inbox import FixtureMailbox
from router import route

CARRIERS = {"bids@skyair.example"}


def test_cost_usd():
    assert llm.cost_usd("gpt-4o-mini", 1000, 100) == pytest.approx(0.00021)


def test_chat_json_parses_and_prices(monkeypatch):
    reply = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=100),
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"origin": "MUC"}', refusal=None))],
    )
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: reply)))
    monkeypatch.setattr(llm, "_client", fake)
    data, cost = llm.chat_json("rfq", "sys", "mail", {"type": "object"}, model="gpt-4o-mini")
    assert data == {"origin": "MUC"}
    assert cost == pytest.approx(0.00021)


def test_gpt_6_luna_runs_without_reasoning(monkeypatch):
    sent = {}
    reply = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=433, completion_tokens=120),
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"origin": "MUC"}', refusal=None))],
    )
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: sent.update(kw) or reply)))
    monkeypatch.setattr(llm, "_client", fake)
    _, cost = llm.chat_json("rfq", "sys", "mail", {"type": "object"}, model="gpt-6-luna")
    assert sent["model"] == "gpt-6-luna" and sent["reasoning_effort"] == "none"
    assert cost == pytest.approx(0.0001033)  # 433 × 0.10 + 120 × 0.50 per 1M tokens


def test_chat_json_rejects_unpriced_model():
    with pytest.raises(KeyError):
        llm.chat_json("rfq", "sys", "mail", {}, model="no-such-model")


@pytest.mark.parametrize(
    "sender, attachments, known_thread, expected",
    [
        ("Tracking <tracking@hackloop.mail>", [], False, "tracking"),
        ("ratedesk@hackloop.mail", [], True, "ratedesk"),
        ("SkyAir <BIDS@skyair.example>", [], True, "carrier_bid"),
        ("bids@skyair.example", [{"filename": "Tariff_Dec.XLSX"}], False, "tariff"),
        ("bids@skyair.example", [], False, "other"),
        ("buyer@customer.example", [], False, "rfq"),
        ("buyer@customer.example", [], True, "customer_reply"),
    ],
)
def test_route(sender, attachments, known_thread, expected):
    mail = {"from": sender, "attachments": attachments}
    assert route(mail, CARRIERS, known_thread) == expected


def test_fixture_mailbox_delivers_each_mail_once_and_replies_in_thread(tmp_path):
    mail = {"id": "m1", "thread_id": "t1", "from": "buyer@customer.example", "subject": "RFQ MUC-JFK", "body": "…"}
    (tmp_path / "m1.json").write_text(json.dumps(mail))
    box = FixtureMailbox(tmp_path)
    assert box.fetch() == [mail]
    assert box.fetch() == []
    box.reply(mail, "Our quote: EUR 1,856.00 all-in")
    assert box.sent == [{"to": "buyer@customer.example", "thread_id": "t1",
                         "subject": "Re: RFQ MUC-JFK", "body": "Our quote: EUR 1,856.00 all-in"}]


def test_a_restart_resumes_rfqs_that_were_being_priced_and_can_still_score(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timedelta, timezone

    import main
    from bids import BidBoard
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *args: started.append((handler.__name__, args[0]["id"], args[-1])))
    fresh = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
    for mail_id, at in ((501, fresh), (502, old), (503, fresh), (504, fresh), (505, fresh)):
        (tmp_path / f"{mail_id}.json").write_text(json.dumps({"id": mail_id, "thread_id": mail_id, "from": "c@x",
                                                              "subject": "RFQ", "body": "…", "received_at": at}))

    class Api:
        def sessions(self):
            return [{"id": 1, "thread_id": "501", "stage": "pricing", "received_at": fresh},  # resumed
                    {"id": 2, "thread_id": "502", "stage": "pricing", "received_at": old},    # expired
                    {"id": 3, "thread_id": "503", "stage": "quoted", "quote": {"total": 1}},  # already quoted
                    {"id": 4, "thread_id": "504", "stage": "pricing", "needs_human": True},   # a person has it
                    {"id": 5, "thread_id": "999", "stage": "new", "received_at": fresh}]     # mail gone: skipped

    assert main.resume_unfinished(FixtureMailbox(tmp_path), Api(), BidBoard(), []) == [1]
    assert started == [("handle_rfq", 501, 1)]  # continues session 1, no new session

    class HandedOver:
        def sessions(self):
            return [{"id": 6, "thread_id": "505", "stage": "pricing", "received_at": fresh, "needs_human": True,
                     "rfq": {"origin": "MUC"}},                                                      # fallback
                    {"id": 7, "thread_id": "503", "stage": "failed", "received_at": fresh}]         # no rfq: skip

    started.clear()
    monkeypatch.setattr(main, "_start", lambda handler, *args: started.append((handler.__name__, args[0]["id"])))
    assert main.resume_unfinished(FixtureMailbox(tmp_path), HandedOver(), BidBoard(), []) == [6]
    assert started == [("fallback_after_restart", 6)]  # its fallback timer died with the worker
