"""FX_FALLBACK: a carrier bid in a currency the portal never stated (CHF, GBP, USD after a fresh start) is compared at a
fallback rate instead of dropped; the rate the portal states always wins."""

import pricing
from booking import BookingError, _check_price
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
    _check_price({"total": "2410.00", "currency": "EUR"}, quote, "R-1")  # within MAX_FRESH_INCREASE of EUR 2,400
    try:
        _check_price({"total": "2780.00", "currency": "EUR"}, quote, "R-1")  # EUR 2,780 is far above EUR 2,400
    except BookingError:
        return
    raise AssertionError("a fresh rate far above the EUR quote must go to a person")
