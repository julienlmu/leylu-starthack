"""The next trap variants 5U is likely to send (sweep of Sat 23:20): what is fixed here, and xfail(strict) for the
gaps still open. Rules only, no LLM call (every call is refused)."""

from datetime import date

import pytest

import airports
import booking_agent
import extract
import gate
import llm
import units
from booking_agent import is_status_question, read_intent
from dg import dg_info

XF = lambda reason: pytest.mark.xfail(strict=True, reason=reason)  # noqa: E731
QUOTE = {"total": 2400.0, "currency": "EUR", "carrier": "SkyAir", "rate_id": "R-1"}


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (calls.append(a[0]), ({"intent": "accept"}, 0.0001))[1])
    return calls


# ---- COUNTER_OFFER: a yes that names another price never books our price --------------------------------------------
@pytest.mark.parametrize("text", ["We'd accept at 1,800 EUR.", "OK for EUR 1,900, go ahead", "accept at 1800€",
                                  "Yes, book it for 2.000,00 EUR please"])
def test_a_counter_offer_is_no_yes(text):
    assert read_intent(text, QUOTE)[0] == "question"


@pytest.mark.parametrize("text", ["Yes book it", "Yes, EUR 2,400.00 is fine, book it", "Go ahead with the 2.400,00 EUR offer",
                                  "ok book, 3 pallets 640 kg as quoted", "Yes, book it. PO 4711."])
def test_our_own_price_or_other_numbers_stay_a_yes(text):
    assert read_intent(text, QUOTE) == ("accept", 0.0)


@pytest.mark.parametrize("text", ["Can you do EUR 1,800?", "Our budget is 2k, can you work with that?",
                                  "Our budget is 2k.", "Could you do it for 1800 euros? Then we book.",
                                  "Yes, if you can beat 2,100 EUR", "OK, book it at EUR 1,950."])
def test_a_counter_offer_never_books_and_never_gets_our_quote_again(text, tmp_path, monkeypatch):
    from inbox import FixtureMailbox
    from test_booking_tracking import REPLY, SESSION, FakeApi, _fake_llm
    monkeypatch.setattr(booking_agent.llm, "chat_json", _fake_llm("accept", "quote_again"))  # the model's worst case
    box, api = FixtureMailbox(tmp_path), FakeApi([SESSION])
    booking_agent.handle_customer_reply({**REPLY, "body": text}, box, api, SESSION)
    assert api.booked == [] and box.sent == [] and "needs_human" in api.events, text


def test_counter_offer_off_is_the_old_behaviour(monkeypatch):
    monkeypatch.setattr(booking_agent, "COUNTER_OFFER", False)
    assert read_intent("We'd accept at 1,800 EUR.", QUOTE)[0] == "accept"


# ---- WEEKDAY_DEADLINE and budget wording ------------------------------------------------------------------------------
READY = date(2026, 11, 23)  # a Monday


@pytest.mark.parametrize("text, due", [
    ("needed in ORD by Friday 28.11.", date(2026, 11, 28)), ("must arrive by Friday", date(2026, 11, 27)),
    ("has to be delivered before Wednesday", date(2026, 11, 25)), ("bis Freitag in Chicago", date(2026, 11, 27)),
    ("must arrive by next Thursday", date(2026, 11, 26)), ("must arrive by 30.11.", date(2026, 11, 30)),
])
def test_weekday_deadlines(text, due):
    assert gate.deadline(text, READY) == due


def test_a_weekday_that_is_no_deadline_is_ignored():
    assert gate.deadline("Pickup on Friday, ready at our dock.", READY) is None


@pytest.mark.parametrize("text, cap", [("we can't pay more than 2000 euros", 2000.0), ("not over EUR 2,000", 2000.0),
                                       ("max 2.000,- EUR", 2000.0), ("fastest option but max budget EUR 2,000", 2000.0)])
def test_budget_wording(text, cap):
    assert gate.budget(text) == cap


def test_relative_week_deadline():  # RELATIVE_DEADLINE: next week counts from the mail (Wed 18 Nov), not the ready date
    assert gate.deadline("has to be there by end of next week", READY, date(2026, 11, 18)) == date(2026, 11, 27)
    assert gate.deadline("has to be there by end of next week", READY, date(2026, 11, 25)) == date(2026, 12, 4)


# ---- FEET_GRAMS ---------------------------------------------------------------------------------------------------------
RAW = {"origin": "FRA", "destination": "ORD", "ask": "cheapest", "pickup_address": None, "ready_date": "2026-11-25",
       "pieces": [{"count": 2, "length": 4, "width": 3, "height": 2, "weight": 300, "weight_is_total": False,
                   "volume": None, "volume_is_total": True}], "dim_unit": "in", "weight_unit": "kg", "volume_unit": "m3",
       "volume": None, "commodity": "machine parts", "dangerous_goods": False, "customer_reference": None,
       "language": "en"}


@pytest.mark.parametrize("body", ["2 crates, 4 x 3 x 2 ft, 300 kg each", "2 crates 4' x 3' x 2', 300 kg each",
                                  "2 crates, 4x3x2 feet, 300 kg each"])
def test_feet(body):
    raw = units.ground({**RAW, "pieces": [dict(RAW["pieces"][0])]}, {"body": body, "subject": "RFQ"})
    piece = extract.to_rfq(raw)[0]["pieces"][0]
    assert raw["dim_unit"] == "ft" and (piece["length_cm"], piece["width_cm"], piece["height_cm"]) == (121.9, 91.4, 61.0)


@pytest.mark.parametrize("body", ["2 crates, dims '120 x 90 x 60', 300 kg each", "2 crates 120x90x60 cm, 300 kg each, 4 ft3"])
def test_no_feet_from_a_quote_mark_or_cubic_feet(body):
    raw = units.ground({**RAW, "dim_unit": "cm", "pieces": [{**RAW["pieces"][0], "length": 120, "width": 90, "height": 60}]},
                       {"body": body, "subject": "RFQ"})
    assert raw["dim_unit"] == "cm"


def test_paper_grammage_is_no_weight_in_grams():
    raw = {**RAW, "pieces": [{**RAW["pieces"][0], "count": 1, "weight": 80, "weight_is_total": True}]}
    assert units.ground(raw, {"body": "1 pallet of 80 g/m² paper, 80 kg", "subject": "RFQ"})["weight_unit"] == "kg"


def test_grams():
    raw = {**RAW, "pieces": [{**RAW["pieces"][0], "count": 20, "weight": 500, "length": None, "width": None,
                              "height": None}]}
    raw = units.ground(raw, {"body": "20 boxes of 500 g each", "subject": "RFQ"})
    assert raw["weight_unit"] == "g" and extract.to_rfq(raw)[0]["pieces"][0]["weight_kg"] == 0.5


def test_the_model_may_answer_ft_and_g():
    props = extract.SCHEMA["properties"]
    assert "ft" in props["dim_unit"]["enum"] and "g" in props["weight_unit"]["enum"]


# ---- AIRPORT_TYPOS ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value, code", [("EDDF", "FRA"), ("KORD", "ORD"), ("kjfk", "JFK"), ("fra", "FRA"),
                                         ("Frankfrut", "FRA"), ("Munchen", "MUC"), ("Chicgo", "ORD"),
                                         ("Shanghi", "PVG"), ("New Yrok", "JFK"), ("Bangkock", "BKK")])
def test_airport_spellings(value, code):
    assert airports.city_code(value)[0] == code


@pytest.mark.parametrize("value", ["MCU", "Paris", "Berlin", "Madrid", "FAR", "Atlantis", "Homburg", "Bad Homburg"])
def test_no_guess_for_a_code_or_a_city_we_dont_fly(value):
    assert airports.city_code(value) == (value, None)


# ---- DG_VEHICLES ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["car engine (used, drained)", "2 used cars", "3 motorcycles", "spare engines",
                                  "camping stove gas cartridges", "hair spray", "bleach, 20 l", "petrol generator",
                                  "Austauschmotor"])
def test_engines_vehicles_and_household_dg(text):
    assert dg_info(text)


@pytest.mark.parametrize("text", ["engine parts", "car parts", "motorcycle helmets", "motorcycle parts", "new car tyres",
                                  "bleached cotton", "Motorradteile", "engine oil filters", "search engine brochures",
                                  "electric vehicle chargers", "vehicle parts", "used vehicle parts"])
def test_parts_are_not_dg(text):
    assert dg_info(text) is None


# ---- LANGUAGE_RULES -------------------------------------------------------------------------------------------------------
def lang(body, read, mail_language=None):
    """As read_request: the customer's ask (rules) first, else the body's script, else the model's reading."""
    rfq = {"language": read, "mail_language": mail_language or read}
    return extract.reply_language(None, body) or extract.script_language({"body": body}, rfq)


def test_chinese_body_with_english_signature_is_zh():
    assert lang("您好，请报价从PVG到FRA的空运，3托盘，640公斤，下周一可提货。\n\nBest regards,\nLi Wei\nShanghai Trading Co.", "en") == "zh"


def test_english_greeting_german_body_keeps_the_models_de():
    assert lang("Hi team,\n\nbitte um ein Angebot FRA-ORD, 3 Paletten, 640 kg.\n\nViele Grüße\nTobias", "de") == "de"


def test_french_reply_quoting_our_english_mail_keeps_fr():
    assert lang("Bonjour, merci, pouvez-vous coter 3 palettes de 640 kg ?\n\n> Hi, thanks for your request.", "fr") == "fr"


def test_english_body_with_a_japanese_attachment_is_en():
    assert lang("Please quote FRA to NRT, packing list attached (Japanese).", "ja") == "en"


def test_reply_in_english_wins():
    assert lang("Guten Tag, bitte Angebot FRA-ORD, 3 Paletten. Please reply in English, our buyer is in Chicago.", "de") == "en"


def test_japanese_body_is_ja():
    assert lang("FRAからORDまでの航空輸送の見積もりをお願いします。パレット3個、640kg。", "en") == "ja"


def test_language_rules_off(monkeypatch):
    monkeypatch.setattr(extract, "LANGUAGE_RULES", False)
    assert lang("您好，请报价从PVG到FRA的空运，3托盘，640公斤。", "en") == "en"


def test_the_models_reading_of_an_ask_or_a_same_script_language_stays():
    assert lang("Please quote FRA-NRT, 3 pallets.", "ja", mail_language="en") == "ja"  # the model read an ask
    assert lang("Добрий день, прошу ціну FRA-ORD, 3 палети, 640 кг.", "uk") == "uk"  # Ukrainian, not Russian
    assert lang("FRAからORDまでの見積もり、宜しくお願い致します。", "ja") == "ja"


# ---- still open (xfail strict: they flip to XPASS the day they're fixed) ------------------------------------------------
@pytest.mark.parametrize("text", ["Où en est mon envoi ?", "¿Dónde está mi envío?", "A che punto è la spedizione?"])
def test_status_question_other_languages(text):
    assert is_status_question(text)


def test_foreign_pickup_zone():  # FOREIGN_PICKUP (more cases: test_next_traps_15b.py)
    assert extract.zone_airport({"address": "Industriestr. 5, 6020 Innsbruck, Austria"}) is not None


R86 = ("Hi there,\n\nHope your day's going well! Sorry for the change-the final packing list came in, and the shipment "
       "details have changed to:\n\n5 pieces, 1317 kg gross weight, 8.18 cbm\n\nEverything else stays the same. Could you "
       "please update your offer?\n\nCheers,\nKlaus Weidner")


def test_r86_new_figures_after_our_quote_get_a_new_quote(tmp_path, monkeypatch):
    from inbox import FixtureMailbox
    from test_booking_tracking import REPLY, SESSION, FakeApi
    import rfq_agent
    seen = []
    monkeypatch.setattr(rfq_agent, "requote_after_change", lambda mail, box, api, session, ask=False: seen.append(mail["body"]))
    box, api = FixtureMailbox(tmp_path), FakeApi([SESSION])
    booking_agent.handle_customer_reply({**REPLY, "body": R86}, box, api, SESSION)
    assert seen == [R86] and api.booked == []
    seen.clear()
    booking_agent.handle_customer_reply({**REPLY, "body": "Thanks, could you also tell me the AWB?"}, box, api, SESSION)
    assert seen == []


def test_requote_off_hands_over_as_before(tmp_path, monkeypatch):
    from inbox import FixtureMailbox
    from test_booking_tracking import REPLY, SESSION, FakeApi
    import rfq_agent
    monkeypatch.setattr(booking_agent, "REQUOTE", False)
    monkeypatch.setattr(rfq_agent, "requote_after_change", lambda *a: (_ for _ in ()).throw(AssertionError("called")))
    box, api = FixtureMailbox(tmp_path), FakeApi([SESSION])
    booking_agent.handle_customer_reply({**REPLY, "body": R86}, box, api, SESSION)
    assert api.booked == []
