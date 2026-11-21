"""QUOTE_CURRENCY: "please quote in USD/CHF/GBP" → the quote is written in that currency at the rate /api/price states
(the portal's, else FX_FALLBACK), instead of a hold that sends the EUR quote after 4 minutes."""

import pytest

import gate

OPTION = {"source": "sheet", "carrier": "Kestrel Airways", "rate_id": None, "currency": "EUR", "total": 2400.0,
          "total_eur": 2400.0, "transit_days": 5, "breakdown": []}
RESULT = {"options": [OPTION], "chosen": OPTION, "fx": {"USD": 0.86, "CHF": 1.07, "GBP": 1.15}}
RFQ = {"ask": "cheapest", "ready_date": "2026-11-25", "pieces": [], "language": "en"}


def review(body, result=RESULT, texts=()):
    return gate.review(dict(RFQ), result, {"subject": "RFQ FRA-GRU", "body": body}, texts)


@pytest.mark.parametrize("body, code, total", [
    ("Please quote in USD.", "USD", 2790.70),
    ("Can you price this in USD?", "USD", 2790.70),
    ("Angebot bitte in CHF.", "CHF", 2242.99),
    ("Quotation in USD please.", "USD", 2790.70),
    ("We need the quote in USD.", "USD", 2790.70),
    ("Hi Lena, quote in CHF please, 3 pallets FRA to GRU.", "CHF", 2242.99),
    ("Please quote in USD for our shipment.", "USD", 2790.70),
    ("Kindly send your offer in US dollars.", "USD", 2790.70),
    ("Prices in CHF please.", "CHF", 2242.99),
    ("Bitte das Angebot in Schweizer Franken.", "CHF", 2242.99),
    ("Could you quote in GBP?", "GBP", 2086.96),
])
def test_the_quote_is_written_in_the_currency_asked(body, code, total):
    verdict = review(body)
    assert (verdict["chosen"]["currency"], verdict["chosen"]["total"]) == (code, total)
    assert verdict["chosen"]["total_eur"] == 2400.0 and not verdict["hold"]
    text, more = gate.finish(f"Our offer: {code} {total:,.2f} all-in.", verdict, RFQ)
    assert more == []  # one amount, the currency named


def test_a_packing_list_value_in_usd_does_not_change_the_quote_currency():
    verdict = review("3 pieces FRA to GRU, cheapest please.", texts=["Commercial invoice: total value in USD 12,000"])
    assert verdict["chosen"]["currency"] == "EUR"


def test_no_rate_for_the_asked_currency_keeps_the_old_hold():
    verdict = review("Please quote in CHF.", {**RESULT, "fx": {"USD": 0.86}})
    assert verdict["chosen"]["currency"] == "EUR" and verdict["hold"]


def test_quote_currency_off_keeps_the_old_hold(monkeypatch):
    monkeypatch.setattr(gate, "QUOTE_CURRENCY", False)
    verdict = review("Please quote in USD.")
    assert verdict["chosen"]["currency"] == "EUR" and verdict["hold"]


def test_an_eur_request_stays_eur():
    assert review("Please quote in EUR, cheapest option.")["chosen"]["currency"] == "EUR"


@pytest.mark.parametrize("body", [
    "The commercial invoice value is quoted in USD 12,400.",  # the reviewer's cases (#125)
    "Goods value: price in USD 8,000 as per invoice.",
    "Our customs value is priced in dollars.",
    "Unit price in USD: 45.00",
    "Please quote in EUR, not in USD.",
    "We usually get quotes in USD, but a quote in EUR is fine.",
    "No need to quote in USD.",
    "Bitte das Angebot nicht in USD, sondern in EUR.",
    "Insurance value: please quote in USD 5,000 cover.",
    "Our budget is USD 3,000.",
    "Please quote in EUR (not in USD).",  # Julien's review of 7ab5053
    "Unit price of the goods in USD: 45.00",
    "Offer in euros please, goods priced in CHF.",
    "Item price in USD: 45.",  # Julien's review of 9558c5f
    "Product price in USD: 1,200",
    "Purchase price in USD: 8,000",
    "Article price in CHF: 30",
    "Price in USD: 45 per item",
    "Preise in USD: 45 pro Stück",
    "Prices in USD would not be accepted.",
    "Our offer in USD to the end client was 50k.",
    "Our invoice is in USD.",
    "Warenwert in USD.",
    "Please do not quote in USD.",
    "The supplier's quote in USD was too high.",  # Julien's review of 60a6c52: someone else's quote
    "Last year's quotation in USD from another forwarder was 3,000.",
    "Our quote in USD to the client is already out.",
    "The Angebot in CHF from your competitor was cheaper.",
])
def test_a_currency_that_is_not_asked_for_the_quote_keeps_it_in_eur(body):
    verdict = review(body)
    assert verdict["chosen"]["currency"] == "EUR" and verdict["chosen"]["total"] == 2400.0
