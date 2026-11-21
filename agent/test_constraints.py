"""Customer constraints (constraints.py): round 42 was rejected `excluded_airline`. The same mistake must not come back
in other words, and a plain mention of an airline must never exclude it."""

import pytest

import constraints
import exclusions
import extract as extract_mod
import gate
import rfq_agent
from bids import BidBoard
from carriers import load_carriers
from inbox import FixtureMailbox
from test_rfq_agent import CARRIERS, MAIL, OPTION, RAW, FakeApi

KIT = load_carriers()  # the start kit's 29 airlines and 22 truckers


def read(text):
    return constraints.read(text, KIT)


@pytest.mark.parametrize("text, names", [
    ("Please do not offer Zephyr Steppe Cargo (ZS) for this shipment or for any of our future inquiries.",
     ["Zephyr Steppe Cargo"]),
    ("We don't want to fly with Lumen Air.", ["Lumen Air Cargo"]),
    ("Please exclude Lumen.", ["Lumen Air Cargo"]),
    ("Any airline except Lumen Air Cargo.", ["Lumen Air Cargo"]),
    ("Any carrier other than Lumen Air Cargo is fine.", ["Lumen Air Cargo"]),
    ("Lumen Air Cargo is not acceptable for us.", ["Lumen Air Cargo"]),
    ("Lumen Air Cargo should not be used.", ["Lumen Air Cargo"]),
    ("No Lumen Air Cargo please.", ["Lumen Air Cargo"]),
    ("Avoid Lumen Air Cargo.", ["Lumen Air Cargo"]),
    ("Never again with Lumen Air Cargo.", ["Lumen Air Cargo"]),
    ("Do not use Lumen, Zephyr or Aurelia.", ["Lumen Air Cargo", "Zephyr Steppe Cargo", "Aurelia Air Cargo"]),
    ("Lumen Air Cargo, not Zephyr.", ["Zephyr Steppe Cargo"]),
    ("Please do not use LM for this shipment, any other airline is fine.", ["Lumen Air Cargo"]),
    ("Bitte nicht mit Lumen Air Cargo.", ["Lumen Air Cargo"]),
    ("Bitte keine Angebote von Lumen Air Cargo.", ["Lumen Air Cargo"]),
    ("Lumen Air Cargo kommt nicht in Frage.", ["Lumen Air Cargo"]),
    ("Ohne Lumen Air Cargo bitte.", ["Lumen Air Cargo"]),
    ("Alle Airlines außer Lumen Air Cargo.", ["Lumen Air Cargo"]),
    ("Lumen Air Cargo bitte ausschließen.", ["Lumen Air Cargo"]),
    ("Weder Lumen noch Zephyr.", ["Lumen Air Cargo", "Zephyr Steppe Cargo"]),
    ("Wir wollen keine Lumen Air Cargo Flüge.", ["Lumen Air Cargo"]),
    ("Taunusfracht should not be used for the pickup.", ["Taunusfracht"]),
    ("Bitte nicht Taunusfracht für die Abholung.", ["Taunusfracht"]),
])
def test_an_excluded_carrier_is_found_in_other_words(text, names):
    found = read(text)
    assert [n for n in found["excluded"] if len(n) > 2] == names
    assert found["required"] == []


@pytest.mark.parametrize("text", [
    "We do not mind which airline, Lumen Air was great last time.",  # the reviewer's three (#115)
    "Wir sind nicht festgelegt, gerne auch Lumen Air.",
    "Avoid delays please, we used Lumen Air before.",
    "We do not mind which airline, Lumen Air Cargo was great last time.",  # the same with the full name
    "Wir sind nicht festgelegt, gerne auch Lumen Air Cargo.",
    "Avoid delays please, we used Lumen Air Cargo before.",
    "Bitte nur mit Lumen Air Cargo, keine Umladung.",  # only Lumen: the one airline they want
    "Lumen Air Cargo was great last time.",
    "No problem with Lumen Air Cargo.",
    "Kein Problem mit Lumen Air Cargo.",
    "Wir haben nichts gegen Lumen Air Cargo.",
    "Please don't hesitate to call. Lumen Air Cargo flew our last order.",
    "Not only Lumen Air Cargo, others are fine too.",
    "If Lumen Air Cargo is not an option, any other airline is fine.",
    "Wenn Lumen Air Cargo nicht kann, gerne eine andere Airline.",
    "Please do not offer Zephyr, Lumen Air Cargo is fine.",  # only Zephyr
    "Please do not offer Zephyr Steppe Cargo, Lumen Air Cargo is fine.",  # main's rule excluded both
    "No PL attached, the packing list follows.",  # PL is Polaris' code, but not in a sentence about airlines
])
def test_a_plain_mention_never_excludes_the_airline(text):
    assert "Lumen Air Cargo" not in read(text)["excluded"]
    assert "Polaris Air Logistics" not in read(text)["excluded"]


@pytest.mark.parametrize("text", [
    "Only Lumen Air Cargo please.", "Please book only with Lumen Air Cargo.", "This must fly with Lumen Air Cargo.",
    "Lumen Air Cargo only.", "Bitte nur mit Lumen Air Cargo.", "Ausschließlich Lumen Air Cargo.",
    "Bitte nur mit Lumen Air Cargo, keine Umladung.",
])
def test_a_required_airline_is_found_and_not_excluded(text):
    found = read(text)
    assert found["required"] == ["Lumen Air Cargo"] and found["excluded"] == []


def test_an_exclusion_is_remembered_only_when_the_customer_says_so():
    assert read("Please do not offer Lumen Air Cargo for this shipment.")["remember"] == []
    assert read("Please do not offer Lumen Air Cargo for any of our future inquiries.")["remember"][0] == "Lumen Air Cargo"
    assert read("Lumen Air Cargo bitte ausschließen, auch künftig.")["remember"][0] == "Lumen Air Cargo"
    assert read("Bitte nie wieder Lumen Air Cargo.")["remember"][0] == "Lumen Air Cargo"


@pytest.mark.parametrize("text, days, strict", [
    ("Transit time max. 3 days.", 3, False), ("Transit must not exceed 4 days.", 4, False),
    ("No more than 5 days in transit please.", 5, False), ("Transit time under 4 days.", 4, True),
    ("Transit time: 3 days maximum.", 3, False), ("Transit time at most three days.", 3, False),
    ("Laufzeit maximal 3 Tage.", 3, False), ("Die Transitzeit darf 5 Tage nicht überschreiten.", 5, False),
    ("Laufzeit höchstens 4 Tage.", 4, False), ("Transitzeit unter 4 Tagen.", 4, True),
])
def test_a_maximum_transit_time_is_read(text, days, strict):
    found = read(text)
    assert (found["max_transit_days"], found["transit_strict"]) == (days, strict)


@pytest.mark.parametrize("text", [
    "Please reply within 2 days.", "Cargo ready within 3 days, pickup in Bremen.", "Ihr Angebot bitte innerhalb von 2 Tagen.",
    "Transit via Frankfurt is fine.",
])
def test_other_day_counts_are_no_transit_limit(text):
    assert read(text)["max_transit_days"] is None


def test_routing_wishes_we_cannot_check_are_a_note():
    assert any("Direct flights only" in n for n in read("Direct flights only, not via DXB.")["notes"])
    assert any("keine Umladung" in n for n in read("Bitte nur mit Lumen Air Cargo, keine Umladung.")["notes"])
    assert read("We'd prefer Lumen Air Cargo if possible.")["required"] == []


# ---- the gate: the options that keep the constraints, before the pick ---------------------------------------------

def opt(carrier, total, days, code=None, pickup=None):
    return {"source": "portal", "carrier": carrier, "airline_code": code, "rate_id": f"R-{carrier[:3]}",
            "currency": "EUR", "total": total, "transit_days": days, "breakdown": [],
            **({"pickup": {"carrier": pickup, "total": 90.0}} if pickup else {})}


OPTIONS = [opt("Zephyr Steppe Cargo", 1500.0, 5), opt("Lumen Air Cargo", 1800.0, 3, "LM"),
           opt("Aurelia Air Cargo", 2100.0, 2, "AU")]
QUOTE_MAIL = {"subject": "RFQ", "body": "2 crates to ULN."}


def review(rfq, options=OPTIONS):
    rfq = {"ask": "cheapest", "ready_date": "2026-11-23", "pieces": [], **rfq}
    return gate.review(rfq, {"options": options, "chosen": min(options, key=lambda o: o["total"])}, QUOTE_MAIL)


def test_the_gate_quotes_the_required_airline():
    verdict = review({"required_carriers": ["Lumen Air Cargo"]})
    assert verdict["chosen"]["carrier"] == "Lumen Air Cargo" and not verdict["hold"]


def test_the_gate_never_quotes_an_excluded_airline_even_if_the_backend_did():
    verdict = review({"excluded_airlines": ["Zephyr Steppe Cargo"]})
    assert verdict["chosen"]["carrier"] == "Lumen Air Cargo" and not verdict["hold"]
    assert review({"excluded_airlines": ["LM", "zephyr steppe cargo"]})["chosen"]["carrier"] == "Aurelia Air Cargo"


def test_the_gate_drops_an_option_with_an_excluded_trucker():
    options = [opt("Zephyr Steppe Cargo", 1500.0, 5, pickup="Taunusfracht"), opt("Lumen Air Cargo", 1800.0, 3)]
    assert review({"excluded_airlines": ["Taunusfracht"]}, options)["chosen"]["carrier"] == "Lumen Air Cargo"


def test_the_gate_keeps_the_maximum_transit_time():
    assert review({"max_transit_days": 3})["chosen"]["carrier"] == "Lumen Air Cargo"
    assert review({"max_transit_days": 2.5})["chosen"]["carrier"] == "Aurelia Air Cargo"  # "under 3 days"


def test_no_option_that_keeps_the_constraint_goes_to_a_person():
    verdict = review({"required_carriers": ["Ibisair Cargo"]})
    assert verdict["hold"] and any(f["code"] == "required_carrier" for f in verdict["findings"])
    assert review({"max_transit_days": 1})["hold"]


def test_constraints_off_restores_the_old_gate(monkeypatch):
    monkeypatch.setattr(constraints, "ON", False)
    assert review({"required_carriers": ["Lumen Air Cargo"]})["chosen"]["carrier"] == "Zephyr Steppe Cargo"


# ---- the RFQ agent: read, remembered, priced -----------------------------------------------------------------------

def run(tmp_path, monkeypatch, extra, sender=None):
    monkeypatch.setattr(exclusions, "STORE", tmp_path / "ex.json")
    monkeypatch.setattr(rfq_agent, "GATE_AUTO_SEND_SECONDS", 0)  # a held quote goes out at once in tests
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**RAW, "pickup_address": None}, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    mail = {**MAIL, "body": MAIL["body"] + "\n\n" + extra, **({"from": sender} if sender else {})}
    rfq_agent.handle_rfq(mail, box, api, BidBoard(), CARRIERS, cutoff_s=0.1)
    return box, api


def test_only_this_airline_is_not_an_exclusion(tmp_path, monkeypatch):
    box, api = run(tmp_path, monkeypatch, "Bitte nur mit CloudCargo, keine Umladung.")
    assert "rates@cloud.example" in [m["to"] for m in box.sent]  # asked for a bid
    assert "excluded_airlines" not in api.data["extracted"]
    assert api.data["extracted"]["required_carriers"] == ["CloudCargo"]


def test_a_one_shipment_exclusion_is_not_remembered(tmp_path, monkeypatch):
    run(tmp_path, monkeypatch, "Please do not offer CloudCargo for this shipment.")
    assert exclusions.known(MAIL["from"]) == []
    run(tmp_path, monkeypatch, "Please do not offer CloudCargo for any of our future inquiries.")
    assert exclusions.known(MAIL["from"]) == ["CloudCargo"]


def test_a_remembered_exclusion_applies_to_the_next_rfq_of_that_customer(tmp_path, monkeypatch):
    run(tmp_path, monkeypatch, "Please do not offer CloudCargo, now or in future inquiries.")
    box, api = run(tmp_path, monkeypatch, "")  # a new thread, no word about airlines
    assert api.data["extracted"]["excluded_airlines"] == ["CloudCargo"]
    assert "rates@cloud.example" not in [m["to"] for m in box.sent]
