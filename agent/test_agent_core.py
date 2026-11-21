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
