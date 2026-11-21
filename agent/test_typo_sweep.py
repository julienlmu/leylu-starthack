"""Typos, regional variants and slang through the rule-based readers (DG words, booking intent, units, spam filter,
constraints), with the look-alikes that must not fire. The LLM extraction copes with typos; these rules must too."""

import pytest

import booking_agent
import constraints
import dg
import extract
import gate
import router
import units
from carriers import load_carriers

KIT = load_carriers()


def dg_hit(text):
    m = gate._first_hit(gate.DG_V2, text) or gate._class_hit(text)
    return m.group(0) if m else None


@pytest.mark.parametrize("text", [
    "lithum batteries", "lithiun ion cells", "litium battery packs", "lithuim batteries", "lithim batteries",
    "lithium-ion baterries", "dangerous good", "dangerus goods", "dangerouse goods", "hazardus materials",
    "hazardious goods", "aersol cans", "aerosoles", "perfum samples", "industrial adhesiv", "flamable liquid",
    "flammabel", "flammables", "inflamable paint", "corossive liquid", "corrosiv", "corrosives", "dry-ice", "dryice",
    "packed in dry-ice", "UN 348O", "UN 3O91", "UN3480.", "UN 3 480", "U.N. 3480", "U.N.3480", "un3480", "Klase 9",
    "Gefahrguet", "Gefaehrgut", "Gefahrengut", "Lithium Ionen Akku", "li-ion packs", "lipo batteries", "dg cargo",
    "haz cargo", "hazmat-y stuff",
])
def test_dg_typos_and_slang_are_dg_in_the_gate_and_before_pricing(text):
    assert dg_hit(text), text
    assert dg.dg_info(text), text


@pytest.mark.parametrize("text", [
    "no dangerus goods", "non-flamable", "kein Gefahrengut", "Gefahrguet: nein", "lithum-free", "no dry-ice",
    "no haz cargo", "not dg cargo", "no corossive items", "non hazardus goods", "no lithum batteries, no perfum",
    "Klase 9: no", "Ref U.N. 3480", "PO UN 348O", "united nations", "Unilever", "dry cleaning", "lipstick",
    "lipoprotein samples", "Lippo Group", "hazard lights", "Hazel Smith", "Hazard Group Ltd", "lithography plates",
    "litigation documents", "flamingo figurines", "Dg. Meyer", "dryer parts", "Klasse 9a students",
    "machine parts 3480 kg", "general cargo",
])
def test_dg_look_alikes_and_negated_typos_are_no_dg(text):
    assert not dg_hit(text), text
    assert not dg.dg_info(text), text


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a, **k: ({"intent": "llm"}, 0.0))


@pytest.mark.parametrize("text", [
    "yep", "yup", "yeah go for it", "sounds good, book it", "lets do it", "let's do it", "go ahaed", "plz book",
    "pls proceed", "bookit", "ok book", "👍 book it", "passt, buchen", "jo, passt", "geht klar", "gebongt",
    "passt scho", "isch guet, bueche", "passt, buchen S' bitte", "ja bitte buche", "bokk it", "we acept",
    "procced pls", "please procede", "confrim", "go for it", "ja, gerne", "sounds good", "approved",
])
def test_slang_and_typo_yes_is_a_yes_without_the_llm(no_llm, text):
    assert booking_agent.read_intent(text) == ("accept", 0.0), text


@pytest.mark.parametrize("text", [
    "nope", "nah", "pass on this one", "too pricey", "zu teuer", "lassen wir", "lassen wir lieber", "nö", "Nein danke",
    "Nee, danke", "we'll pass", "we will pass", "forget it", "we went with another forwarder", "nope, too much",
])
def test_slang_no_is_a_decline_without_the_llm(no_llm, text):
    assert booking_agent.read_intent(text) == ("decline", 0.0), text


@pytest.mark.parametrize("text", [
    "yep but change pickup to Monday", "yep if transit under 3 days", "ok if the price stays", "yes, unless it is late",
    "jo, aber noch nicht buchen", "passt, aber bitte Abholung am Montag", "not yet, hold on", "don't book yet",
    "yeah, quick question first: is customs included?", "nope, we'll go ahead later", "nah, go ahead", "yeah no",
    "ok, I'll check internally and get back to you", "sounds good, we'll check with the team", "passt nicht",
    "we pass the documents to the airline", "lassen wir es so", "Gefahrgut: nein", "mach ma",
])
def test_slang_yes_never_fires_on_conditions_changes_or_later(no_llm, text):
    assert booking_agent.read_intent(text)[0] != "accept", text
    if text in ("we pass the documents to the airline", "lassen wir es so", "Gefahrgut: nein"):
        assert booking_agent.read_intent(text)[0] != "decline", text


@pytest.mark.parametrize("text, unit", [
    ("500 kgs", "kg"), ("500 kilos", "kg"), ("500 kilo", "kg"), ("500 Kilogramm", "kg"), ("500 KG.", "kg"),
    ("500 k g", "kg"), ("2 tonnes", "t"), ("2 tons", "t"), ("1100 lbs", "lb"), ("2.5 cbm", "m3"), ("2.5 m3", "m3"),
    ("2.5 m³", "m3"), ("2,5 kubik", "m3"), ("2,5 Kubikmeter", "m3"),
])
def test_unit_written_next_to_the_number(text, unit):
    units_all = {**units.WEIGHT_UNITS, **units.VOLUME_UNITS}
    assert units._unit_after(text, units.NUMBER.search(text), units_all) == unit


@pytest.mark.parametrize("text", ["3 pallettes", "3 palettes", "3 palets", "3 plts", "3 Stk", "3 Kolli", "3 colli",
                                  "4 ctns", "3 Paletten", "500 Kilogramm", "2,5 Kubikmeter"])
def test_count_words_are_cargo_facts(text):
    assert extract.CARGO_FACT.search(text) and router.HARD_FACT.search(text) and router.SHIPMENT_SIGNAL.search(text)


@pytest.mark.parametrize("body", [
    "pls qoute 2 palets frankfurt to dubai asap", "need rate 4 plts FRA-DXB",
    "can u qoute 3 crates 200 kgs to dubai, promo price ok?", "hey need price 5 boxes 80 kilo to LA, discount code?",
    "hi pls send best rate for 2 plts 700kg muc-ord, newsletter subscriber here",
    "need a qoute, 3 pallettes, 900 kgs, FRA to JFK, winner gets the job!", "hi need prise for 2 Stk 300 kg nach NYC",
    "1 plt 200kgs FRA to BOM, click here for the packing list", "3 Kolli 50 kilo HAM-SIN, special offer?",
])
def test_slang_rfq_is_never_spam(body):
    assert not router.is_spam({"subject": "", "body": body, "from": "x@y.z", "attachments": []})


@pytest.mark.parametrize("text", ["dont use Lumen", "no Zephyr pls", "nicht mit Zephyr bitte", "pls no Lumen",
                                  "kein Zephyr bitte", "ohne Lumen bitte", "Lumen not acceptable", "Zephyr bitte nicht",
                                  "plz avoid Lumen", "don't quote Zephyr"])
def test_slang_exclusion_still_excludes(text):
    assert constraints.read(text, KIT)["excluded"], text
