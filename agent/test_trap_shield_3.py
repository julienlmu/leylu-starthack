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


# 5. Net/gross: 5U already writes "Lot 2: 4 cartons, each 48 kg gross (41 kg net)" (r12, r63)
LOS = ("Hi,\n\nCould you quote the cheapest air freight option to LOS (Lagos, NG) for automotive sensors?\n\n"
       "Lot 1: 4 drums, together 730 kg gross (642 kg net), together 1.68 cbm\n"
       "Lot 2: 4 cartons, each 48 kg gross (41 kg net), each 110 x 110 x 52 cm\n"
       "Lot 3: 5 cases, each 206 kg gross (191 kg net), each 120 x 100 x 8 cm\n\nMira Petersen")


def _gross(body, pieces):
    rfq = {"pieces": [dict(count=c, weight_kg=w, length_cm=None, width_cm=None, height_cm=None) for c, w in pieces]}
    note = extract.prefer_gross(rfq, {"subject": "", "body": body})
    return round(sum(p["count"] * p["weight_kg"] for p in rfq["pieces"]), 2), note


@pytest.mark.parametrize("pieces", [[(1, 642), (4, 41), (5, 191)], [(1, 642), (4, 48), (5, 206)],
                                    [(4, 160.5), (4, 48), (5, 206)], [(1, 730), (4, 48), (5, 191)]])
def test_a_lot_read_as_net_is_priced_gross(pieces):
    total, note = _gross(LOS, pieces)
    assert total == 1952 and note


def test_a_gross_reading_is_left_alone():
    assert _gross(LOS, [(1, 730), (4, 48), (5, 206)]) == (1952, None)


@pytest.mark.parametrize("body,pieces,want", [
    ("11 pieces, net weight 450 kg, gross weight 520 kg, 3.1 cbm", [(11, 450 / 11)], 520),
    ("Gewicht: 1.250 kg netto, 1.390 kg brutto", [(1, 1250)], 1390),
    ("4 pallets, each N.W. 180 kg, G.W. 205 kg", [(4, 180)], 820),
    ("gross weight 676 kg, chargeable weight (1:5000) 1,160 kg", [(1, 1160)], 676),
    ("Total gross weight 1,250 kg, volume weight 1,670 kg", [(1, 1670)], 1250),
    ("poids net 300 kg, poids brut 340 kg", [(1, 300)], 340),
    ("tare 25 kg per pallet, net 500 kg", [(1, 500)], 500),  # no gross written: nothing to correct
    ("Gross 704 kg", [(1, 704)], 704),
])
def test_net_tare_and_chargeable_figures(body, pieces, want):
    assert _gross(body, pieces)[0] == want


# 6. A 502 / timeout while sending the quote no longer loses the round
def _box(handler, monkeypatch, tmp_path):
    import httpx
    import inbox
    monkeypatch.setattr(inbox.time, "sleep", lambda s: None)
    box = inbox.FiveUMailbox(key="k", state_file=str(tmp_path / "since"))
    box.http = httpx.Client(base_url="http://5u.test", transport=httpx.MockTransport(handler))
    return box


def test_a_502_on_send_is_retried(monkeypatch, tmp_path):
    import httpx
    answers = iter([httpx.Response(502), httpx.Response(200, json={"id": 7})])
    box = _box(lambda request: next(answers), monkeypatch, tmp_path)
    assert box.send("a@b", "s", "b") == 7


def test_a_timeout_on_send_is_retried(monkeypatch, tmp_path):
    import httpx
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("slow")
        return httpx.Response(200, json={"id": 8})
    assert _box(handler, monkeypatch, tmp_path).send("a@b", "s", "b") == 8


def test_a_400_is_not_retried(monkeypatch, tmp_path):
    import httpx
    calls = []
    box = _box(lambda request: calls.append(1) or httpx.Response(400), monkeypatch, tmp_path)
    with pytest.raises(httpx.HTTPStatusError):
        box.send("a@b", "s", "b")
    assert len(calls) == 1


def test_a_server_down_for_good_still_raises(monkeypatch, tmp_path):
    import httpx
    calls = []
    box = _box(lambda request: calls.append(1) or httpx.Response(503), monkeypatch, tmp_path)
    with pytest.raises(httpx.HTTPStatusError):
        box.send("a@b", "s", "b")
    assert len(calls) == 3


# 7. "Quote in USD" in any language (since R72 5U writes RFQs in any language)
@pytest.mark.parametrize("text,code", [
    ("Merci de nous faire une offre en dollars américains.", "USD"), ("Pourriez-vous coter en USD ?", "USD"),
    ("¿Podrían cotizar en dólares (USD)?", "USD"), ("Potreste quotare in dollari USA?", "USD"),
    ("Graag een offerte in USD.", "USD"), ("Proszę o wycenę w USD.", "USD"), ("Fiyatı USD olarak verebilir misiniz?", "USD"),
    ("请用美元报价。", "USD"), ("能否请您用美元报一个全包价？", "USD"), ("米ドル建てでお見積もりをお願いします。", "USD"),
    ("Пожалуйста, укажите цену в долларах США.", "USD"), ("يرجى تقديم السعر بالدولار الأمريكي.", "USD"),
    ("달러로 견적 부탁드립니다.", "USD"), ("Merci de coter en francs suisses.", "CHF"), ("请用英镑报价。", "GBP"),
    ("Please quote in EUR.", None), ("请用欧元报价。", None), ("Our invoice value is USD 12,000.", None),
    ("请用人民币报价。", "CNY"), ("日本円でお見積もりをお願いします。", "JPY"),  # gate: rate → converted, else held
    ("La valeur de la marchandise est de 12 000 USD, merci pour votre devis.", None), ("货值为 20,000 美元，请报价。", None),
    ("Ne pas coter en dollars, uniquement en euros.", None),
    ("Could you quote the fastest option? The goods are worth USD 8,000.", None),
])
def test_currency_asked_in_any_language(text, code):
    assert gate.asked_currency(normalize(text)) == code


# 8. Review of #229
def test_a_net_figure_that_is_another_lots_gross_never_rewrites_a_right_reading():
    body = "Lot 1: 3 pallets, each 160 kg gross (142 kg net)\nLot 2: 2 crates, each 142 kg gross (130 kg net)"
    assert _gross(body, [(3, 160), (2, 142)]) == (764, None)


@pytest.mark.parametrize("body,pieces,want", [
    ("Net weight: 450 kg Gross weight: 520 kg", [(1, 450)], 520),  # a table row: 450 must not also be "gross"
    ("4 pallets, 180 kg N.W. / 205 kg G.W.", [(4, 180)], 820),  # dotted labels after the number
    ("Lot 1 730 kg gross (642 kg net)", [(1, 642)], 730),  # the lot number is no thousands group
])
def test_label_layouts(body, pieces, want):
    assert _gross(body, pieces)[0] == want


@pytest.mark.parametrize("text,code", [
    ("We pay our suppliers in USD via our corporate account.", None),  # "corporate" is no "rate"
    ("Accurate dimensions follow; our accounts are kept in USD.", None),
    ("Separate pickup please, billing in USD.", None),
    ("Please quote in U.S. dollars.", "USD"), ("Please quote in USD. The goods value is 5000 EUR.", "USD"),
    ("请用美元报价。谢谢", "USD"), ("Cheapest option please, quote in USD.", "USD"),
])
def test_currency_review_cases(text, code):
    assert gate.asked_currency(normalize(text)) == code


def test_a_transient_retry_waits_a_full_poll_gap(monkeypatch, tmp_path):
    import httpx
    import inbox
    waits = []
    box = _box(lambda request: next(answers), monkeypatch, tmp_path)
    monkeypatch.setattr(inbox.time, "sleep", waits.append)
    answers = iter([httpx.Response(502), httpx.Response(200, json={"id": 9})])
    assert box.send("a@b", "s", "b") == 9 and waits and min(waits) >= 5.5
