"""INSURANCE (session 93 too_low): the cargo insurance premium the customer asks for is part of the all-in.
Rules only, no LLM. The whole RFQ path is in test_traps.py (evals/traps.json, "session 93 …")."""

import httpx
import pytest

import backend
import insurance

S93 = ("Please include cargo insurance in the all-in price: goods value 22000 EUR, insured at 110 % of that value, "
       "premium rate 0.40 %.")


@pytest.mark.parametrize("text, value, cover, rate, minimum, premium", [
    (S93, 22000, 1.1, 0.004, None, 96.80),
    ("Insurance: please include it. Invoice value EUR 18,500.00, cover 110% of CIF value, premium 0.35%, minimum "
     "premium EUR 50.", 18500, 1.1, 0.0035, 50, 71.23),
    ("Please add insurance to the all-in. Goods value is 5.000 EUR, rate 0,5 %, minimum premium 45 EUR.",
     5000, 1.0, 0.005, 45, 45.0),
    ("Bitte inkl. Transportversicherung: Warenwert 40.000 EUR, Prämie 0,3 %.", 40000, 1.0, 0.003, None, 120.0),
    ("All-in incl. insurance please, cargo value EUR 12k, premium 3 ‰.", 12000, 1.0, 0.003, None, 36.0),
])
def test_terms_and_premium(text, value, cover, rate, minimum, premium):
    t = insurance.terms(text)
    assert t["complete"] and t["value"] == value and t["currency"] == "EUR"
    assert t["cover"] == pytest.approx(cover) and t["rate"] == pytest.approx(rate) and t["minimum"] == minimum
    assert insurance.premium(t) == pytest.approx(premium, abs=0.01)


@pytest.mark.parametrize("text", [
    "No insurance needed, we have our own cover.",
    "We insure it ourselves.",
    "Could you quote insurance separately?",
    "Insurance is not required.",
    "Please send the insurance certificate after booking.",  # no ask to put it in the price
    "Thanks, Anna\nMüller Versicherungsmakler GmbH",
    "3 pallets, 715 kg, FRA to ORD, cheapest please.",
])
def test_no_insurance_ask(text):
    assert insurance.terms(text) is None


def test_an_ask_without_terms_is_incomplete():
    t = insurance.terms("Please include cargo insurance in the all-in price.")
    assert t["asked"] and not t["complete"] and insurance.premium(t) is None


def test_a_value_in_another_currency_uses_the_price_results_rate():
    t = insurance.terms("Goods value USD 30,000, insured at 110%, premium rate 0.4%. Please include insurance.")
    assert t["currency"] == "USD" and insurance.premium(t) is None  # no rate: never a guess
    assert insurance.premium(t, {"USD": 0.92}) == pytest.approx(121.44)


def _result():
    a = {"carrier": "Aurora Cargo", "rate_id": "R-93A", "currency": "EUR", "total": 927.95, "transit_days": 3,
         "breakdown": [{"label": "Air freight", "amount": 927.95}]}
    b = {"carrier": "Condor Freight", "rate_id": "R-93B", "currency": "EUR", "total": 1080.10, "transit_days": 2,
         "breakdown": [{"label": "Air freight", "amount": 1080.10}]}
    return {"options": [a, b], "chosen": a, "why": "cheapest"}


def test_add_puts_the_premium_into_every_all_in_once():
    rfq = {"insurance": insurance.terms(S93)}
    result = insurance.add(_result(), rfq)
    assert [o["total"] for o in result["options"]] == [1024.75, 1176.90] and result["chosen"]["total"] == 1024.75
    assert result["chosen"]["insurance"]["total"] == 96.80
    assert sum(line["amount"] for line in result["chosen"]["breakdown"]) == pytest.approx(1024.75)
    assert insurance.add(result, rfq)["chosen"]["total"] == 1024.75  # a second call adds nothing


def test_add_without_an_ask_or_switched_off_changes_nothing(monkeypatch):
    assert insurance.add(_result(), {})["chosen"]["total"] == 927.95
    rfq = {"insurance": insurance.terms(S93)}
    monkeypatch.setattr(insurance, "ON", False)
    assert insurance.add(_result(), rfq)["chosen"]["total"] == 927.95 and insurance.terms(S93) is None


def test_the_backend_client_adds_the_premium_on_every_price_call():
    client = backend.Backend("http://backend.test")
    client.http = httpx.Client(base_url="http://backend.test",
                               transport=httpx.MockTransport(lambda request: httpx.Response(200, json=_result())))
    result = client.price({"origin": "DUS", "destination": "MEX", "insurance": insurance.terms(S93)}, [])
    assert result["chosen"]["total"] == 1024.75 and "Cargo insurance EUR 96.80" in result["why"]
