"""Live rounds that lost price points (postmortem docs/postmortem/sessions_r85_r91.json on orhun/postmortem-r85-r91)."""
import re

import extract as extract_mod
import insurance
import rfq_agent
import shapes
from inbox import FixtureMailbox
from test_rfq_agent import FakeApi

R91 = ("Hi,\n\nCould you quote the fastest air freight option from DUS to MEX (Mexico City, MX) and confirm the transit "
       "time? Please include the all-in price in EUR.\n\nWe'll deliver to DUS ourselves. The shipment is ready on "
       "2026-11-29: 1 piece of printed marketing material, 176 kg gross, 1.26 cbm.\n\nPlease include cargo insurance in "
       "the all-in price, on the terms of our frame agreement: goods value 22000 EUR, insured at 110 % of that value, "
       "premium rate 0.40 %.\n\nSara\nLindqvist Medtech")
R89 = ("Hi there,\n\nHope your week's going well! Could you quote the fastest air freight option for each of these two "
       "shipments? Both will be ready for pickup on 2026-11-23 at our site in Wiesbaden, Germany (postcode 65996). Please "
       "arrange the truck from our site to the airport as part of the quote.\n\n1. GRU (Sao Paulo, BR) - automotive "
       "sensors, 4 pieces, gross weight 1281 kg, volume 3.76 cbm.\n2. TLV (Tel Aviv, IL) - machine parts, 1 piece, gross "
       "weight 1812 kg, volume 5.75 cbm.\n\nCould you send both quotes in the same reply, with a separate all-in price in "
       "EUR for each shipment rather than a combined total?\n\nThanks for your help!\n\nPetra Hofmann")
XENON = {"source": "portal", "leg": "air", "carrier": "Xenon Cargo Airlines", "rate_id": "R-SVio", "currency": "EUR",
         "total": 927.95, "total_eur": 927.95, "transit_days": 2, "valid_until": "2026-11-30",
         "chargeable_weight_kg": 210.42, "breakdown": [{"label": "Air freight", "amount": 927.95}]}
RAW91 = {"origin": "DUS", "destination": "MEX", "ask": "fastest", "pickup_address": None, "ready_date": "2026-11-29",
         "pieces": [{"count": 1, "length": None, "width": None, "height": None, "weight": 176, "weight_is_total": True}],
         "dim_unit": "cm", "weight_unit": "kg", "volume_unit": "m3", "volume": 1.26,
         "commodity": "printed marketing material", "dangerous_goods": False, "customer_reference": None, "language": "en"}


def test_r91_the_asked_insurance_is_in_the_all_in_price(tmp_path, monkeypatch):
    assert insurance.terms(R91)["premium"] == 96.80  # 22000 × 110 % × 0.40 %
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (dict(RAW91), 0.0))
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [dict(XENON)], "chosen": dict(XENON), "why": "fastest"})
    rfq_agent.handle_rfq({"id": "m91", "thread_id": "t91", "from": "sara@lindqvist.example",
                          "subject": "Fastest air freight option: DUS to MEX", "body": R91}, box, api)
    [sent] = box.sent
    assert re.findall(r"\d[\d,]*\.\d{2}", sent["body"]) == ["1,024.75"]  # 927.95 + 96.80, still one amount


def test_insurance_terms_and_non_asks():
    assert insurance.terms("Goods value EUR 15,000. Insurance CIF + 10 %, premium 0.3 %, minimum premium EUR 60.")["premium"] == 60
    assert insurance.terms("Warenwert 18.000 EUR, bitte Versicherung einschließen, Prämie 0,5 %.")["premium"] == 90
    assert insurance.terms("No insurance needed. Goods value 22000 EUR, premium rate 0.4 %.") is None
    assert insurance.terms("Please include insurance, goods value 22000 EUR.") is None  # no rate: never guessed
    assert insurance.terms("Goods value 22000 EUR for customs.") is None
    result = insurance.apply({"options": [dict(XENON)]}, insurance.terms(R91))
    assert result["options"][0]["total"] == 1024.75
    assert insurance.apply(result, insurance.terms(R91))["options"][0]["total"] == 1024.75  # never twice


def test_r89_separate_prices_rather_than_a_combined_total_is_not_one_total():
    assert not shapes._one_total(R89)
    assert shapes._one_total("Please give us one total for both shipments.")
    assert shapes._one_total("We need a combined price for both lots.")
