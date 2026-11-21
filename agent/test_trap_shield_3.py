"""Batu's trap hunt 3 (Sat 23:20): what an LLM-written mail or a real-life shipment still slipped past our rules."""

import pytest

import dg
import extract
import gate
from inbox import normalize


# 1. Text shapes NFKC leaves: U+2011 hyphens, en dashes, curly apostrophes, an HTML body
@pytest.mark.parametrize("raw,check,want", [
    ("must arrive by 2026‑12‑04", gate.deadline, "2026-12-04"),
    ("must arrive by 2026–12–04", gate.deadline, "2026-12-04"),
    ("quote in US‑Dollar please", gate.asked_currency, "USD"),
    ("It’s time‑critical.", extract.ask_from_words, "fastest"),
    ("It’s not time‑critical.", extract.ask_from_words, "cheapest"),
    ("<p>Please quote in USD.</p>", gate.asked_currency, "USD"),
    ("<div>Goods: Li-ion batteries, UN&nbsp;3480, Class&nbsp;9</div>", lambda t: bool(dg.dg_info(t)), True),
    ("It&#8217;s time&#8209;critical", extract.ask_from_words, "fastest"),
])
def test_text_shapes(raw, check, want):
    got = check(normalize(raw))
    assert (got.isoformat() if hasattr(got, "isoformat") else got) == want


def test_html_body_keeps_lines_and_cells():
    text = normalize("<html><body><p>Hello,</p><table><tr><td>Gross weight</td><td>1&nbsp;250 kg</td></tr></table>"
                     "<p>Thanks<br>Anna</p></body></html>")
    assert "Gross weight | 1 250 kg" in text and "Thanks\nAnna" in text and "<" not in text


def test_a_plain_mail_with_a_less_than_sign_is_left_alone():
    assert normalize("weight < 500 kg, height > 1 m") == "weight < 500 kg, height > 1 m"


# 2. Budget: "EUR 1 800" was a budget of EUR 1 (every quote held as over budget)
@pytest.mark.parametrize("text,want", [
    ("not more than EUR 1 800", 1800), ("max. 1'800 EUR", 1800), ("max. 1’800 EUR", 1800),
    ("Budget: EUR 12 500", 12500), ("budget 2k EUR", 2000), ("max EUR 2.5k all-in", 2500),
    ("maximal 2.000,- EUR", 2000), ("our budget is max EUR 2,000", 2000), ("budget: 2.000 €", 2000),
    ("budget EUR 1.234,50", 1234.5), ("max 3,000.00 EUR", 3000), ("budget of EUR 500 for 2 pallets", 500),
    ("not more than EUR 1 800", 1800),
])
def test_budget_formats(text, want):
    assert gate.budget(normalize(text)) == want


def test_swiss_thousands_are_in_the_mail():
    assert 1250.0 in extract._mail_numbers("1'250 kg") and 2450.0 in extract._mail_numbers(normalize("2’450 kg"))


# 3. Real-life DG goods (the attachment DG check is rules only)
@pytest.mark.parametrize("goods", [
    "lighters", "butane gas cartridges", "compressed air cylinders", "refrigerant gas R134a", "liquid nitrogen",
    "nitrous oxide", "whipped cream chargers", "gasoline", "petrol", "diesel fuel", "kerosene", "lamp oil",
    "white spirit", "turpentine", "xylene", "toluene", "formaldehyde", "hand sanitiser", "alcohol gel", "disinfectant",
    "essential oils", "aftershave", "hairspray", "carburettor cleaner", "polyester resin", "epoxy resin",
    "caustic soda", "sodium hypochlorite", "bleach", "ammonia solution", "ammonium nitrate fertilizer",
    "organic peroxide", "chlorine tablets", "pepper spray", "calcium carbide", "magnesium powder", "activated carbon",
    "sparklers", "signal flares", "life rafts", "sodium-ion batteries", "battery packs",
    "rechargeable batteries", "electric wheelchairs", "blood samples",
    "diagnostic specimens", "asbestos", "motorcycles", "used cars", "lawn mowers", "chainsaws", "outboard motor",
    "engines with fuel residue", "Benzin 20 l Kanister", "Kältemittel R410A", "Akkus für E-Bikes", "Notstromaggregat",
    "pool chemicals", "portable power stations",
])
def test_real_life_dg_goods(goods):
    assert dg.dg_info(f"Commodity: {goods}")


@pytest.mark.parametrize("goods", [
    "machine parts", "engine parts", "spare parts for motorcycles", "motorcycle helmets", "fuel filters",
    "tablets (vitamin supplements)", "paper notebooks", "laptop bags", "phone cases", "drone propellers",
    "battery chargers", "lawn mower blades", "chainsaw chains", "the weight matches the packing list",
    "acid-free paper", "alcohol-free mouthwash", "resin pellets (PP)", "charcoal grey sweaters", "bleach-free cotton",
    "carbon dioxide emissions report", "Motorenteile", "no lithium batteries, no fuel", "non-flammable cleaning agent",
    "Contains no batteries. Not dangerous goods.", "petrol-free cleaning agent", "automotive sensors",
    # a battery inside a product is PI 967 Section II: no DGD (team decision, test_cargo_price_sweep xfail)
    "laptops", "smartphones", "cordless drills", "Akku-Bohrschrauber", "drones", "electronic control units",
])
def test_ordinary_goods_stay_ordinary(goods):
    assert dg.dg_info(f"Commodity: {goods}") is None


# 4. Frankfurt (Oder) is not our Frankfurt am Main zone
@pytest.mark.parametrize("town,zone", [("Frankfurt (Oder)", None), ("Frankfurt/Oder", None),
                                       ("Frankfurt an der Oder", None), ("Frankfurt", "60"), ("Frankfurt am Main", "60")])
def test_frankfurt_oder(town, zone):
    assert extract.city_zone(town) == zone
