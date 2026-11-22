"""Pricing traps through the real RFQ path (extraction faked, nothing sent for real, no LLM): a hard constraint no option
keeps, DG an airline refuses, cold chain, budget, deadline, FX deciding a close race, tariff validity, transit wording.

Scoring: a quote that breaks a hard constraint is rejected, a quote that never goes out scores 0. So when no option
keeps a must (only Ibisair, every airline excluded, DG refused): one question without an amount, then a person.
"""

import re
import threading
import time

import pytest

import bids
import exclusions
import extract as extract_mod
import gate
import llm
import rfq_agent
from bids import BidBoard
from carriers import KIT_LIST, load_carriers
from inbox import FixtureMailbox
from test_traps import BASE_RAW, GateApi

KIT = load_carriers(KIT_LIST)
MONEY = re.compile(r"\d[\d,.]*\.\d{2}")


def opt(carrier, total, days, code=None, breakdown=()):
    return {"source": "portal", "leg": "air", "carrier": carrier, "airline_code": code, "rate_id": f"R-{carrier[:3]}",
            "currency": "EUR", "total": total, "transit_days": days, "valid_until": "2026-11-30",
            "breakdown": list(breakdown)}


ORD = [opt("Aurelia Air Cargo", 2000.0, 3, "AU"), opt("Xenon Cargo Airlines", 2150.0, 2, "XC")]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM call")))
    monkeypatch.setattr(exclusions, "STORE", tmp_path / "exclusions.json")
    monkeypatch.setattr(rfq_agent, "GATE_AUTO_SEND_SECONDS", 0.0)  # the dead man's switch fires at once
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0.0)
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: None)


def run(tmp_path, monkeypatch, body, options=ORD, chosen=0, raw=None, carriers=KIT, thread="t-trap"):
    raw = {**BASE_RAW, "origin": "CGN", "destination": "ORD", **(raw or {})}
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    api = GateApi({"options": options, "chosen": options[chosen], "why": "test"})
    box = FixtureMailbox(tmp_path)
    mail = {"id": "m1", "thread_id": thread, "from": "buyer@customer.example", "subject": "Air freight quote",
            "body": body, "attachments": []}
    rfq_agent.handle_rfq(mail, box, api, BidBoard(), carriers, cutoff_s=0)
    return [m for m in box.sent if m["thread_id"] == thread], api


def quoted(api):
    return (api.data.get("quote_sent") or {}).get("option") if "quote_sent" in api.events else None


# ---- 1. a required airline with no option on the lane ---------------------------------------------------------------

def test_only_ibisair_without_an_ibisair_option_asks_instead_of_quoting_another_airline(tmp_path, monkeypatch):
    sent, api = run(tmp_path, monkeypatch, "Please quote CGN to ORD, 3 pieces 715 kg. We only fly with Ibisair Cargo.")
    assert len(sent) == 1 and "quote_sent" not in api.events
    assert MONEY.findall(sent[0]["body"]) == [] and "Ibisair" in sent[0]["body"]
    assert "Aurelia" not in sent[0]["body"] and "needs_human" in api.events


def test_only_aurelia_with_an_aurelia_option_quotes_it(tmp_path, monkeypatch):
    sent, api = run(tmp_path, monkeypatch, "Please quote CGN to ORD. Only Xenon Cargo Airlines please.")
    assert quoted(api)["carrier"] == "Xenon Cargo Airlines" and MONEY.findall(sent[0]["body"]) == ["2,150.00"]


def test_every_airline_excluded_asks_too(tmp_path, monkeypatch):
    sent, api = run(tmp_path, monkeypatch, "CGN to ORD please. Do not offer Aurelia Air Cargo or Xenon Cargo Airlines.")
    assert "quote_sent" not in api.events and len(sent) == 1 and MONEY.findall(sent[0]["body"]) == []


# ---- 2. dangerous goods an airline refuses -------------------------------------------------------------------------

def test_a_bid_that_refuses_dg_is_never_quoted_for_dg(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (
        {**BASE_RAW, "origin": "CGN", "destination": "ORD", "dangerous_goods": True}, 0.0001))
    carriers = [{"name": "Aurelia Air Cargo", "email": "au@x.example", "kind": "airline", "serves": ["*"]},
                {"name": "Xenon Cargo Airlines", "email": "xc@x.example", "kind": "airline", "serves": ["*"]}]

    class PricingApi(GateApi):
        def price(self, rfq, bids=None, fallback=False):  # the backend: every bid an option, cheapest chosen
            options = sorted([opt(b["carrier"], b["total"], b["transit_days"]) for b in bids or []],
                             key=lambda o: o["total"])
            return {"options": options, "chosen": options[0] if options else None, "why": "test"}

    api, box, board = PricingApi({}), FixtureMailbox(tmp_path), BidBoard()
    mail = {"id": "m1", "thread_id": "t-dg", "from": "buyer@customer.example", "subject": "RFQ",
            "body": "3 pieces, 715 kg lithium batteries UN3480, CGN to ORD.", "attachments": []}
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(mail, box, api, board, carriers, 3))
    worker.start()
    give_up = time.time() + 2
    while len(box.sent) < 2 and time.time() < give_up:
        time.sleep(0.01)
    replies = {"au@x.example": "Total: EUR 1,500.00 all-in, transit 3 days. Please note we do not accept dangerous "
                               "goods on this lane.",
               "xc@x.example": "Total: EUR 1,900.00 all-in, transit 2 days."}
    for request in list(box.sent):
        board.deliver({"thread_id": request["thread_id"], "body": replies[request["to"]]})
    worker.join(timeout=5)
    assert quoted(api)["carrier"] == "Xenon Cargo Airlines", api.texts


@pytest.mark.parametrize("text, total", [
    ("Total: EUR 1,200.00 all-in\nPlus DG surcharge EUR 150.00\nTransit 3 days", 1350.0),
    ("Air freight all-in EUR 1,200.00\nDG surcharge: EUR 150.00\nTransit 3 days", 1350.0),
    ("All-in EUR 1,200.00 (DG surcharge EUR 150.00 included)", 1200.0),
    ("Total: EUR 1,350.00 all-in, incl. DG surcharge EUR 150.00", 1350.0),
    ("Total: EUR 1,200.00\nTransit 3 days", 1200.0),
])
def test_a_dg_surcharge_written_apart_is_part_of_the_bid(text, total):
    assert bids.parse_bid(text, 500)["total"] == total


# ---- 3. temperature-controlled cargo: no capability data, so no promise ---------------------------------------------

def test_cold_chain_is_not_promised_for_an_airline_we_cannot_check(tmp_path, monkeypatch):
    sent, api = run(tmp_path, monkeypatch, "CGN to ORD, 3 pieces 715 kg vaccines, must be kept at 2-8 °C.", carriers=())
    body = sent[0]["body"]
    assert "quote_sent" in api.events and "temperature" in body.lower()
    assert not re.search(r"we book (?:them|it) as temperature-controlled", body), body


# ---- 5. every option above the budget ------------------------------------------------------------------------------

def test_over_budget_quote_says_so_in_words(tmp_path, monkeypatch):
    sent, api = run(tmp_path, monkeypatch, "CGN to ORD, 715 kg. Our budget is max EUR 1,500 all-in.", carriers=())
    body = sent[0]["body"]
    assert "budget" in body.lower() and MONEY.findall(body) == ["2,000.00"], body


def test_within_budget_no_budget_sentence(tmp_path, monkeypatch):
    sent, api = run(tmp_path, monkeypatch, "CGN to ORD, 715 kg. Our budget is max EUR 2,500 all-in.", carriers=())
    assert "budget" not in sent[0]["body"].lower()


# ---- 6. no option meets the arrival deadline -----------------------------------------------------------------------

def test_a_missed_deadline_is_said_never_implied(tmp_path, monkeypatch):
    sent, api = run(tmp_path, monkeypatch, "CGN to ORD, 715 kg, ready 25 Nov. Must arrive by 2026-11-26.",
                    carriers=())
    body = sent[0]["body"]
    assert "deadline" in {f["code"] for f in api.findings} and len(MONEY.findall(body)) == 1
    assert re.search(r"none of .{0,60} in time", body), body


def test_a_met_deadline_has_no_such_sentence(tmp_path, monkeypatch):
    sent, api = run(tmp_path, monkeypatch, "CGN to ORD, 715 kg, ready 25 Nov. Must arrive by 2026-11-30.",
                    carriers=())
    assert "in time" not in sent[0]["body"]


# ---- 8. FX decides a close race -------------------------------------------------------------------------------------

def test_a_close_race_decided_by_an_estimated_fx_rate_is_flagged_not_blocked(tmp_path, monkeypatch):
    usd = opt("Xenon Cargo Airlines", 2010.0, 3, breakdown=[
        {"label": "Air freight Xenon Cargo Airlines (bid): USD 2,337.21 × 0.86 EUR/USD", "amount": 2010.0}])
    eur = opt("Aurelia Air Cargo", 2040.0, 3, breakdown=[{"label": "Air freight Aurelia", "amount": 2040.0}])
    sent, api = run(tmp_path, monkeypatch, "CGN to ORD, 715 kg.", options=[usd, eur], carriers=())
    assert quoted(api)["carrier"] == "Xenon Cargo Airlines" and not any(t.startswith("Quote held") for t in api.texts)
    assert "fx_close" in {f["code"] for f in api.findings}


def test_a_clear_winner_in_another_currency_is_not_flagged(tmp_path, monkeypatch):
    usd = opt("Xenon Cargo Airlines", 1700.0, 3, breakdown=[
        {"label": "Air freight Xenon (bid): USD 1,976.74 × 0.86 EUR/USD", "amount": 1700.0}])
    sent, api = run(tmp_path, monkeypatch, "CGN to ORD, 715 kg.", options=[usd, ORD[0]], carriers=())
    assert "fx_close" not in {f["code"] for f in api.findings}


# ---- 19. transit over a weekend: never an exact arrival the data can't support ---------------------------------------

def test_the_quote_states_transit_as_about_n_days_not_an_arrival_date(tmp_path, monkeypatch):
    sent, _ = run(tmp_path, monkeypatch, "CGN to ORD, 715 kg, ready Friday 27 Nov.", carriers=(),
                  raw={"ready_date": "2026-11-27"})
    body = sent[0]["body"]
    assert "about 3 days" in body and not re.search(r"\b(?:arrives?|arrival)\b.{0,20}\b\d{1,2}\b", body), body


def test_human_style_says_around_for_the_arrival_day():
    import quote_style
    from datetime import date
    text = quote_style.human_quote_text({"ready_date": "2026-11-27", "origin": "CGN", "destination": "ORD",
                                         "pieces": [{"count": 1}]}, opt("Aurelia Air Cargo", 2000.0, 3),
                                        today=date(2026, 11, 22))
    assert "arrive around" in text and not re.search(r"arrive (?:on|by) \d", text)


# ---- 20. door delivery or DDP is a must ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    "CGN to ORD, 715 kg. Door-to-door delivery to our customer in Chicago is mandatory, DDP.",
    "Please quote DDP Chicago, delivery to the consignee's door is required.",
])
def test_mandatory_door_delivery_is_not_quoted_airport_to_airport(tmp_path, monkeypatch, body):
    sent, api = run(tmp_path, monkeypatch, body, carriers=())
    assert "quote_sent" not in api.events and len(sent) == 1 and MONEY.findall(sent[0]["body"]) == []


def test_door_delivery_as_a_wish_gets_the_not_included_sentence(tmp_path, monkeypatch):
    sent, api = run(tmp_path, monkeypatch, "CGN to ORD, 715 kg, DAP Chicago.", carriers=())
    assert "quote_sent" in api.events and "not included" in sent[0]["body"]
