import pytest

import extract as extract_mod
from extract import ask_from_words, read_request
from test_rfq_agent import RAW


@pytest.mark.parametrize("text, ask", [
    ("Urgent shipment, the line is down.", "fastest"),
    ("We need the fastest option to JFK.", "fastest"),
    ("Time-critical: spare parts for an AOG aircraft.", "fastest"),
    ("Dringende Sendung: bitte die schnellste Verbindung.", "fastest"),
    ("Necesitamos la opción más rápida.", "fastest"),
    ("Please send it by express.", "fastest"),
    ("No rush on this one, please quote your best rate.", "cheapest"),
    ("Not urgent. We are looking for the most economical option.", "cheapest"),
    ("Bitte das günstigste Angebot, es ist nicht eilig.", "cheapest"),
    ("Nous cherchons le moins cher.", "cheapest"),
    ("Please quote for 3 pallets to JFK.", None),  # says neither: the default stays
    ("Urgent shipment, but please the cheapest option.", None),  # says both: the model's reading (or the default) stays
    ("Best regards\nMüller Express GmbH", None),  # a company name is not an ask
    ("Pickup at the earliest on Monday.", None),
    # urgency about our reply, not the transport (review of #87): the default stays
    ("Please send your best offer asap.", None),
    ("We need a quote urgently.", None),
    ("URGENT: quote request FRA-JFK", None),
    ("Kindly revert asap.", None),
    ("Bitte schnellstmöglich ein Angebot.", None),
    ("Please quote ASAP, we need it there as soon as possible.", None),
    ("This one is urgent.", None),  # urgent what? not clear enough to overrule the default
    ("Urgent: please quote the fastest routing.", None),  # the only "fastest" is in a clause about the quote
])
def test_ask_from_the_customers_words(text, ask):
    assert ask_from_words(text) == ask


def _mail(body):
    return {"subject": "RFQ", "body": body, "received_at": "2026-11-21T16:00:00+00:00"}


def test_the_words_only_fill_a_missing_ask(monkeypatch):
    raw = {**RAW, "ask": None, "pickup_address": None,
           "pieces": [{"count": 2, "length": 48, "width": 40, "height": 40, "weight": 440, "weight_is_total": True,
                       "volume": None, "volume_is_total": True}]}
    body = "2 crates, 48 x 40 x 40 in, 440 lb in total, MUC to JFK. Time-critical shipment!"
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    assert read_request(_mail(body))["rfq"]["ask"] == "fastest"
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**raw, "ask": "cheapest"}, 0.0001))
    assert read_request(_mail(body))["rfq"]["ask"] == "cheapest"  # the model read an ask: never overruled
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    monkeypatch.setattr(extract_mod, "ASK_RULES", False)
    assert read_request(_mail(body))["rfq"]["ask"] == "cheapest"  # ASK_RULES=off: the old default
