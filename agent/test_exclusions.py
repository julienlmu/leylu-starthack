import pytest

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


# Round 42's trap comes back reworded (5U escalates a trap in the next rounds: r10 xlsx → r11 PDF)
KIT = ["Zephyr Steppe Cargo", "Meridian Freightways", "Solace Air Cargo", "Lumen Air Cargo", "Nova Atlas Cargo",
       "Spessart Spedition"]
REWORDED = [
    ("Please don't use ZS for this one.", ["ZS"]),
    ("We had a bad experience with Zephyr Steppe Cargo last month, so please choose another carrier.",
     ["Zephyr Steppe Cargo"]),
    ("Zephyr Steppe Cargo is not acceptable to us.", ["Zephyr Steppe Cargo"]),
    ("Zephyr Steppe Cargo should not be used.", ["Zephyr Steppe Cargo"]),
    ("Any airline is fine except Zephyr Steppe Cargo.", ["Zephyr Steppe Cargo"]),
    ("Our compliance team has blacklisted Meridian Freightways.", ["Meridian Freightways"]),
    ("Please keep Meridian Freightways out of the options.", ["Meridian Freightways"]),
    ("Bitte bieten Sie nicht Meridian Freightways an.", ["Meridian Freightways"]),
    ("Meridian Freightways kommt für uns nicht in Frage.", ["Meridian Freightways"]),
    ("Merci de ne pas proposer Meridian Freightways.", ["Meridian Freightways"]),
    ("Por favor, no utilicen Meridian Freightways.", ["Meridian Freightways"]),
    ("We do not want our goods on Meridian Freightways (MD) or Solace Air Cargo.",
     ["Meridian Freightways", "MD", "Solace Air Cargo"]),
    ("Please do not use the trucker Spessart Spedition for the pickup.", ["Spessart Spedition"]),
]
NOT_EXCLUDED = [
    "We only work with Meridian Freightways, please quote them.",
    "We do not mind which airline, Meridian Freightways was great last time.",
    "No objection to Meridian Freightways.",
    "Lumen Air Cargo was great, the price is not acceptable though.",
    "The goods are not dangerous. Please do not use pallets, Lumen Air Cargo knows our boxes.",
    "Please quote without DG surcharges; Nova Atlas Cargo is fine.",
]


@pytest.mark.parametrize("text,expected", REWORDED)
def test_reworded_exclusions_are_found(text, expected):
    assert exclusions.excluded_in(text, KIT) == expected


@pytest.mark.parametrize("text", NOT_EXCLUDED)
def test_mentions_that_exclude_nothing(text):
    assert exclusions.excluded_in(text, KIT) == []


def test_only_one_airline_is_accepted():
    assert exclusions.required_in("We only work with Meridian Freightways, please quote them.", KIT) == [
        "Meridian Freightways"]
    assert exclusions.required_in("Please quote Lumen Air Cargo only, we have a rate agreement.", KIT) == [
        "Lumen Air Cargo"]
    assert exclusions.required_in("Bitte nur mit Lumen Air Cargo, keine Umladung.", KIT) == ["Lumen Air Cargo"]
    assert exclusions.required_in("We have a contract with Solace Air Cargo.", KIT) == ["Solace Air Cargo"]
    assert exclusions.required_in("Only 4 pieces this time, Lumen Air Cargo was fine before.", KIT) == []


def test_extraction_names_map_onto_our_list():
    assert exclusions.known_names(["meridian", "ZS", "Foo Air", "", "DG"], KIT) == [
        "Meridian Freightways", "ZS", "Foo Air"]
    # a name the mail doesn't contain is the model's invention: never exclude the best option on it
    assert exclusions.known_names(["Meridian", "Solace Air Cargo"], KIT, "Please don't use Meridian.") == [
        "Meridian Freightways"]


def _run(tmp_path, monkeypatch, raw_extra=None, body_extra="", attachments=None, attachment_text=""):
    monkeypatch.setattr(exclusions, "STORE", tmp_path / "ex.json")
    monkeypatch.setattr(extract_mod, "extract",
                        lambda mail, model=None: ({**RAW, "pickup_address": None, **(raw_extra or {})}, 0.0001))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    api.attachment_text = lambda filename, content: attachment_text
    mail = {**MAIL, "body": MAIL["body"] + body_extra, "attachments": attachments or []}
    rfq_agent.handle_rfq(mail, box, api, BidBoard(), CARRIERS, cutoff_s=0.1)
    return box, api


def test_the_extraction_finds_an_exclusion_the_regex_misses(tmp_path, monkeypatch):
    """A wording no regex knows ("Con CloudCargo tuvimos problemas") still reaches pricing via the one LLM call."""
    box, api = _run(tmp_path, monkeypatch, {"excluded_carriers": ["cloudcargo"]}, "\n\nCon CloudCargo tuvimos problemas.")
    assert "rates@cloud.example" not in [m["to"] for m in box.sent]
    assert api.data["extracted"]["excluded_airlines"] == ["CloudCargo"]
    assert "mail_excluded_carriers" not in api.data["extracted"]


def test_an_exclusion_in_the_attachment_counts(tmp_path, monkeypatch):
    import base64
    att = [{"filename": "SLI_1.txt", "content_base64": base64.b64encode(b"x").decode()}]
    box, api = _run(tmp_path, monkeypatch, attachments=att,
                    attachment_text="Shipper's letter of instruction\nCarrier: any, except CloudCargo.")
    assert api.data["extracted"]["excluded_airlines"] == ["CloudCargo"]
    assert "rates@cloud.example" not in [m["to"] for m in box.sent]


def test_an_only_airline_reaches_pricing(tmp_path, monkeypatch):
    _, api = _run(tmp_path, monkeypatch, body_extra="\n\nWe only work with SkyAir, please quote them.")
    assert api.data["extracted"]["required_airlines"] == ["SkyAir"]
    assert "excluded_airlines" not in api.data["extracted"]


def test_an_unreadable_attachment_never_breaks_the_rfq(tmp_path, monkeypatch):
    import base64
    att = [{"filename": "scan.jpg", "content_base64": base64.b64encode(b"x").decode()}]
    _, api = _run(tmp_path, monkeypatch, attachments=att, attachment_text=None)
    assert "error" not in api.events and api.data["extracted"]["origin"] == "MUC"
