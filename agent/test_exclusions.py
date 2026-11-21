import exclusions
import rfq_agent
from bids import BidBoard
from inbox import FixtureMailbox
from test_rfq_agent import CARRIERS, MAIL, OPTION, RAW, FakeApi
import extract as extract_mod

R42 = ("Dear Sir or Madam,\n\nCould you please quote your cheapest air freight option to ULN.\n\nPlease do not offer "
       "Zephyr Steppe Cargo (ZS) for this shipment or for any of our future inquiries.\n\nBest regards\nPetra Meyer")


def test_round_42_exclusion_is_found_and_remembered_for_future_inquiries(tmp_path, monkeypatch):
    monkeypatch.setattr(exclusions, "STORE", tmp_path / "ex.json")
    assert exclusions.excluded_in(R42, ["Zephyr Steppe Cargo", "Lumen Air Cargo"]) == ["Zephyr Steppe Cargo", "ZS"]
    assert exclusions.excluded_in("Lumen Air Cargo was great last time.", ["Lumen Air Cargo"]) == []
    exclusions.remember("Meyer@x.example", ["Zephyr Steppe Cargo", "ZS"])
    assert exclusions.known("meyer@x.example") == ["Zephyr Steppe Cargo", "ZS"]  # a later RFQ of the same customer


def test_an_excluded_airline_is_not_asked_and_reaches_pricing(tmp_path, monkeypatch):
    monkeypatch.setattr(exclusions, "STORE", tmp_path / "ex.json")
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**RAW, "pickup_address": None}, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    mail = {**MAIL, "body": MAIL["body"] + "\n\nPlease do not offer CloudCargo for this shipment."}
    rfq_agent.handle_rfq(mail, box, api, BidBoard(), CARRIERS, cutoff_s=0.1)
    assert "rates@cloud.example" not in [m["to"] for m in box.sent]  # not asked for a bid
    assert api.data["extracted"]["excluded_airlines"] == ["CloudCargo"]  # the backend prices without it


def test_the_exclusion_must_govern_the_airline_and_only_future_ones_are_remembered(tmp_path, monkeypatch):
    names = ["Lumen Air", "Lumen Air Cargo", "Fjordline Air Cargo", "Helix Air Freight", "Nova Atlas Cargo"]
    for text in ("We do not mind which airline, Lumen Air was great.", "Please do not use pallets and Lumen Air Cargo was great.",
                 "We don't need Lumen Air Cargo to hurry, any day is fine."):
        assert exclusions.excluded_in(text, names) == [], text
    assert exclusions.excluded_in("Please exclude Fjordline Air Cargo and Helix Air Freight.", names) == [
        "Fjordline Air Cargo", "Helix Air Freight"]
    assert exclusions.excluded_in("Bitte nicht mit Nova Atlas Cargo.", names) == ["Nova Atlas Cargo"]
    assert not exclusions.for_future("Please do not offer Lumen Air Cargo for this shipment.")
    assert exclusions.for_future(R42)


def test_a_one_off_exclusion_is_not_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr(exclusions, "STORE", tmp_path / "ex.json")
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**RAW, "pickup_address": None}, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    mail = {**MAIL, "body": MAIL["body"] + "\n\nPlease do not offer CloudCargo for this shipment."}
    rfq_agent.handle_rfq(mail, box, api, BidBoard(), CARRIERS, cutoff_s=0.1)
    assert "rates@cloud.example" not in [m["to"] for m in box.sent] and exclusions.known(MAIL["from"]) == []
