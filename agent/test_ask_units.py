"""UNIT_ASK: a number the mail writes without any unit is asked about once (no amount), then quoted once from the answer."""
import re
import threading
from datetime import datetime, timedelta, timezone

import pytest

import amendments
import extract as extract_mod
import main
import rfq_agent
import units
from bids import BidBoard
from inbox import FixtureMailbox
from test_rfq_agent import OPTION, RAW, FakeApi

PIECES = [{"count": 3, "length": None, "width": None, "height": None, "weight": 715, "weight_is_total": True}]
UNITLESS = {**RAW, "pickup_address": None, "pieces": PIECES, "volume": 2.65, "weight_unit": "kg", "dim_unit": "cm",
            "language": "en"}
BODY = "Hello,\n\nplease quote MUC to JFK: 3 pallets of machine parts, gross weight 715, 2.65 cbm.\n\nThanks,\nTom Reed"


def iso(ago):
    return (datetime.now(timezone.utc) - timedelta(seconds=ago)).isoformat()


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    rfq_agent._answered.clear()
    amendments._pending.clear()
    monkeypatch.setattr(rfq_agent, "GATE_AUTO_SEND_SECONDS", 0.0)
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: None)
    yield
    rfq_agent._answered.clear()
    amendments._pending.clear()


def ask(raw, body, subject="RFQ"):
    return units.unitless(raw, f"{subject}\n{body}")


@pytest.mark.parametrize("body", ["gross weight 715, 2.65 cbm", "3 pallets, 715, 2.65 cbm", "Gewicht: 715; 2,65 cbm"])
def test_a_weight_without_a_unit_is_asked(body):
    assert ask(UNITLESS, body) == {"weight": {"unit": "kg", "said": "715"}}


@pytest.mark.parametrize("body", ["gross weight 715 kg", "715kgs", "715 Kilo", "715 Kilogramm", "gross 715 lbs",
                                  "715 pounds", "3 pallets 715 KG", "Weight (kg): 715", "715 kg\nSorry, 750 it is",
                                  "pallet 1: 300 kg, pallet 2: 415"])
def test_a_weight_with_a_unit_anywhere_is_not_asked(body):
    assert "weight" not in ask(UNITLESS, body + ", 2.65 cbm")


def test_a_unit_in_the_subject_or_the_attachment_counts():
    assert ask(UNITLESS, "gross weight 715, 2.65 cbm", subject="RFQ 3 plt 715 kg") == {}
    assert units.unitless(UNITLESS, "RFQ\ngross weight 715, 2.65 cbm\nPACKING LIST\nGross weight: 715 kg") == {}
    assert units.unitless({**UNITLESS, "pieces": [{**PIECES[0], "weight": 2}], "weight_unit": "t"}, "2 t, 2.65 cbm") == {}


def test_piece_counts_are_never_weights():
    assert ask(UNITLESS, "3 pallets, gross weight 715 kg, 2.65 cbm") == {}
    assert ask(UNITLESS, "3 pallets, 2.65 cbm") == {}  # 715 is nowhere in the mail: the model's guess, not ours to ask


def test_dimensions_and_volume_without_a_unit():
    raw = {**UNITLESS, "volume": None, "pieces": [{**PIECES[0], "length": 120, "width": 80, "height": 100}]}
    assert ask(raw, "3 pallets 715 kg, dims 120x80x100")["dims"]["said"] == "120x80x100"
    for written in ("120x80x100 cm", "120 x 80 x 100cm", "48x40x40\"", "120x80x100 (cm)", "L x W x H in mm: 120x80x100"):
        assert ask(raw, f"3 pallets 715 kg, dims {written}") == {}, written
    assert ask({**raw, "volume": 2.4}, "715 kg, dims 120x80x100, 2.4 cbm") == {}  # the volume with its unit decides
    vol = {**UNITLESS, "volume": 2.4}
    assert ask(vol, "715 kg, volume 2.4") == {"volume": {"unit": "m3", "said": "2.4"}}
    for written in ("volume 2.4 cbm", "volume 2.4 m³", "Volumen 2,4 m3", "volume: 2.4 cu ft"):
        assert ask({**vol, "volume": 2.4}, "715 kg, " + written) == {}, written


def test_the_answer_is_read_by_rules():
    kinds = {"weight": {}, "dims": {}, "volume": {}}
    assert units.answered("It's kg, sorry", ["weight"]) == {"weight": "kg"}
    assert units.answered("lbs", ["weight"]) == {"weight": "lb"}
    assert units.answered("Kilo natürlich", ["weight"]) == {"weight": "kg"}
    assert units.answered("all metric", kinds) == {"weight": "kg", "dims": "cm", "volume": "m3"}
    assert units.answered("kg and inches", ["weight", "dims"]) == {"weight": "kg", "dims": "in"}
    assert units.answered("not lbs, kg", ["weight"]) == {}  # two units: unclear, a person reads it
    assert units.answered("I'm not sure", ["weight"]) == {}


def run_rfq(monkeypatch, tmp_path, received=30, raw=UNITLESS, body=BODY):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    api = FakeApi({"options": [{**OPTION, "pickup": None}], "chosen": {**OPTION, "pickup": None}, "why": "cheapest"})
    box = FixtureMailbox(tmp_path)
    mail = {"id": "m1", "thread_id": "t1", "from": "buyer@customer.example", "subject": "RFQ MUC-JFK", "body": body,
            "received_at": iso(received), "attachments": []}
    monkeypatch.setattr(box, "get", lambda tid: mail, raising=False)
    rfq_agent.handle_rfq(mail, box, api, BidBoard(), [], cutoff_s=0)
    rfq = next((u["rfq"] for u in api.updates if (u.get("rfq") or {}).get("awaiting") == "units"), None)
    return api, box, rfq, {"id": 1, "thread_id": "t1", "rfq": rfq, "stage": "pricing", "llm_cost_usd": 0.0001}


def answer(text):
    return {"id": "m2", "thread_id": "t1", "from": "buyer@customer.example", "subject": "Re: RFQ MUC-JFK",
            "body": text, "received_at": iso(0), "attachments": []}


def test_the_question_goes_out_without_an_amount_and_nothing_is_priced(monkeypatch, tmp_path):
    api, box, rfq, _ = run_rfq(monkeypatch, tmp_path)
    assert rfq and "quote_sent" not in api.events and len(box.sent) == 1
    body = box.sent[0]["body"]
    assert "715: kg / lbs?" in body and not re.search(r"\d[\d,.]*\.\d{2}|EUR|€", body), body


def test_the_question_speaks_the_customers_language(monkeypatch, tmp_path):
    api, box, rfq, _ = run_rfq(monkeypatch, tmp_path, raw={**UNITLESS, "language": "de"})
    assert box.sent[0]["body"].startswith("Hallo") and "Einheit" in box.sent[0]["body"]


@pytest.mark.parametrize("said, kg", [("kg", 715), ("Sorry, those are lbs", 715 * 0.45359237)])
def test_the_answer_is_quoted_once_in_the_same_session(monkeypatch, tmp_path, said, kg):
    api, box, rfq, session = run_rfq(monkeypatch, tmp_path)
    rfq_agent.resume_after_units(answer(f"Hi,\n\n{said}\n\nTom"), box, api, BidBoard(), [], session)
    assert api.events.count("quote_sent") == 1 and len(box.sent) == 2
    quoted = api.data["extracted"]["pieces"]
    assert round(sum(p["count"] * p["weight_kg"] for p in quoted), 3) == round(kg, 3)


def test_a_second_answer_does_not_quote_twice(monkeypatch, tmp_path):
    api, box, rfq, session = run_rfq(monkeypatch, tmp_path)
    ts = [threading.Thread(target=rfq_agent.resume_after_units,
                           args=({**answer("kg"), "id": f"m{i}"}, box, api, BidBoard(), [], session)) for i in (2, 3)]
    [t.start() for t in ts]
    [t.join(5) for t in ts]
    assert api.events.count("quote_sent") == 1


def test_a_late_answer_is_handed_over(monkeypatch, tmp_path):
    api, box, rfq, session = run_rfq(monkeypatch, tmp_path, received=400)
    rfq_agent.resume_after_units(answer("kg"), box, api, BidBoard(), [], session)
    assert "quote_sent" not in api.events and "needs_human" in api.events


def test_an_answer_without_a_unit_is_handed_over(monkeypatch, tmp_path):
    api, box, rfq, session = run_rfq(monkeypatch, tmp_path)
    rfq_agent.resume_after_units(answer("Thanks, waiting for your price"), box, api, BidBoard(), [], session)
    assert "quote_sent" not in api.events and "needs_human" in api.events


def test_inches_convert_the_dimensions_and_the_volume_from_them():
    rfq = {"pieces": [{"count": 1, "length_cm": 48.0, "width_cm": 40.0, "height_cm": 40.0, "weight_kg": 100.0}],
           "volume_m3": 0.0768}
    out = rfq_agent.with_units(rfq, {"dims": {"unit": "cm", "said": "48x40x40", "volume_from_dims": True}},
                               {"dims": "in"})
    assert out["pieces"][0]["length_cm"] == pytest.approx(121.92) and out["volume_m3"] == pytest.approx(1.2585, 1e-3)
    assert rfq["pieces"][0]["length_cm"] == 48.0  # the stored reading is not changed in place


def test_a_mail_with_its_units_is_quoted_at_once(monkeypatch, tmp_path):
    api, box, rfq, _ = run_rfq(monkeypatch, tmp_path, body=BODY.replace("715", "715 kg"))
    assert rfq is None and api.events.count("quote_sent") == 1


def test_unit_ask_off_quotes_as_before(monkeypatch, tmp_path):
    monkeypatch.setattr(rfq_agent, "UNIT_ASK", False)
    api, box, rfq, _ = run_rfq(monkeypatch, tmp_path)
    assert rfq is None and api.events.count("quote_sent") == 1


def test_the_worker_hands_the_answer_to_the_unit_resume(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *a: started.append(handler.__name__))
    monkeypatch.setattr(main, "route", lambda *a, **k: "customer_reply", raising=False)
    session = {"id": 1, "thread_id": "t1", "stage": "pricing", "rfq": {"awaiting": "units"}}
    api = FakeApi({})
    api.find = lambda tid: session
    main.dispatch(answer("kg"), FixtureMailbox(tmp_path), api, BidBoard(), [])
    assert started == ["resume_after_units"]
