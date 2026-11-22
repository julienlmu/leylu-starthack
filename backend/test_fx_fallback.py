"""FX_FALLBACK: a carrier bid in a currency the portal never stated (CHF, GBP, USD after a fresh start) is compared at a
fallback rate instead of dropped; the rate the portal states always wins."""

import pricing
from booking import PriceChanged, _ask_if_changed
from test_pricing import offline_pricer, price, rfq

LANE = rfq("FRA", "AKL", 1000, 3)  # no sheet, no portal: bids only
BIDS = [{"carrier": "Aurelia Air Cargo", "leg": "air", "currency": "CHF", "total": 2100.0, "transit_days": 2},
        {"carrier": "Borealis Freight", "leg": "air", "currency": "EUR", "total": 2600.0, "transit_days": 2}]


def test_a_chf_bid_is_converted_at_the_fallback_rate_not_dropped():
    result = price(offline_pricer(), LANE, BIDS)
    assert result["chosen"]["carrier"] == "Aurelia Air Cargo"
    assert result["chosen"]["total"] == 2247.0  # 2,100 CHF × 1.07
    assert "fallback rate 1.07 EUR/CHF" in result["why"]
    assert "CHF 2,100.00 × 1.07 EUR/CHF" in result["chosen"]["breakdown"][0]["label"]
    assert result["fx"]["CHF"] == 1.07


def test_the_portal_rate_wins_over_the_fallback():
    pricer = offline_pricer()
    pricer.portal.fx["CHF"] = 1.3
    result = price(pricer, LANE, BIDS)
    assert result["chosen"]["carrier"] == "Borealis Freight"  # 2,100 CHF × 1.3 = EUR 2,730 > EUR 2,600
    assert result["fx"]["CHF"] == 1.3 and "fallback" not in result["why"]


def test_fallback_off_skips_the_bid_as_before(monkeypatch):
    monkeypatch.setattr(pricing, "FX_FALLBACK", {})
    result = price(offline_pricer(), LANE, BIDS)
    assert result["chosen"]["carrier"] == "Borealis Freight"
    assert "unknown currency skipped: Aurelia Air Cargo" in result["why"]


def test_the_fallback_setting_is_parsed():
    assert pricing._fallback_fx("off") == {}
    assert pricing._fallback_fx("chf:1.05, USD:0.9,bad,GBP:x") == {"CHF": 1.05, "USD": 0.9}


def test_a_quote_in_usd_is_checked_in_eur_at_booking():
    quote = {"currency": "USD", "total": 2790.70, "total_eur": 2400.0}  # quoted in USD at 0.86 EUR/USD
    rate = {"rate_id": "R-1", "airline": "Gannet Airways", "currency": "EUR"}
    kept = []
    _ask_if_changed({**rate, "total": "2400.00"}, quote, kept.append)  # the same EUR price: booked, nothing asked
    try:
        _ask_if_changed({**rate, "total": "2410.00"}, quote, kept.append)  # EUR 10 more: asked again, in USD
    except PriceChanged as change:
        assert change.detail["new_total"] == round(2410 * 2790.70 / 2400, 2) and change.detail["currency"] == "USD"
        assert kept == ["R-1"]
        return
    raise AssertionError("another price than the accepted one must be asked again")


def test_the_fixed_table_converts_pln_and_sek_bids_before_ranking():
    bids = [{"carrier": "Aurelia Air Cargo", "leg": "air", "currency": "PLN", "total": 9000.0, "transit_days": 2},
            {"carrier": "Borealis Freight", "leg": "air", "currency": "SEK", "total": 24000.0, "transit_days": 2},
            {"carrier": "Juniper Cargo", "leg": "air", "currency": "EUR", "total": 2200.0, "transit_days": 2}]
    result = price(offline_pricer(), LANE, bids)
    assert result["chosen"]["carrier"] == "Aurelia Air Cargo" and result["chosen"]["total"] == 2115.0  # 9,000 × 0.235
    assert {o["carrier"]: o["total"] for o in result["options"]}["Borealis Freight"] == 2184.0  # 24,000 × 0.091
    assert result["fx"]["PLN"] == 0.235 and result["fx"]["SEK"] == 0.091


def test_an_unknown_currency_is_still_skipped_never_guessed():
    bids = [{"carrier": "Aurelia Air Cargo", "leg": "air", "currency": "XYZ", "total": 10.0, "transit_days": 2},
            {"carrier": "Borealis Freight", "leg": "air", "currency": "EUR", "total": 2600.0, "transit_days": 2}]
    result = price(offline_pricer(), LANE, bids)
    assert result["chosen"]["carrier"] == "Borealis Freight" and "unknown currency skipped" in result["why"]


def test_the_table_lives_in_the_repo_and_env_overrides_one_rate():
    table = pricing._fx_table(pricing.Path(pricing.__file__).resolve().parent / "data" / "fx_eur.csv")
    assert table["USD"] == 0.86 and table["CHF"] == 1.07 and table["GBP"] == 1.15 and len(table) >= 20
