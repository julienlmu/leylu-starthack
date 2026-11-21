from datetime import date

import gate
import quote_style
import templates
from quote_style import human_quote_text

RFQ = {"origin": "CGN", "destination": "DFW", "ask": "fastest", "ready_date": "2026-11-29", "language": "en",
       "pickup": {"address": "51804 Bergisch Gladbach, Germany", "zone": "51"}, "contact_name": "Deniz",
       "pieces": [{"count": 9, "weight_kg": 199.4}], "volume_m3": 12.58, "commodity": "precision instruments",
       "dangerous_goods": False, "customer_reference": None}
OPTION = {"source": "portal", "carrier": "Lumen Air Cargo", "rate_id": "R-1", "currency": "EUR", "total": 6175.48,
          "transit_days": 1.4583, "pickup": {"carrier": "Westfalenroute", "total": 356.10, "transit_days": 0.4583}}
TODAY = date(2026, 11, 21)


def test_round_19_reads_like_a_forwarder_wrote_it():
    text = human_quote_text(RFQ, OPTION, "Hello,\n\nCould you please quote ...\n\nViele Gruesse\nDeniz", today=TODAY)
    assert text.startswith("Hi Deniz,") and "Cologne (CGN)" in text and "Dallas (DFW)" in text
    assert "we collect them in Bergisch Gladbach on 29 November" in text
    assert "leaves on 30 November" in text and "around 1 December" in text
    assert "The all-in price is EUR 6,175.48, including the pickup, air freight, fuel and security." in text
    assert gate.MONEY.findall(text) == ["6,175.48"] and "hour" not in text and "\n- " not in text
    assert text.endswith("Lena Hartmann\nLeylü Air Freight") and 60 <= len(text.split()) <= 130


def test_a_warm_line_only_when_the_customer_wrote_one():
    warm = human_quote_text(RFQ, OPTION, "Hi there,\n\nHope your week's going well! Could you quote ...", today=TODAY)
    assert "hope your week is going well too" in warm or "hope the same for you" in warm
    answer = human_quote_text(RFQ, OPTION, "Hi Lena,\n\nSorry I left out the pickup location: Augsburg.", today=TODAY)
    assert "address" in answer.split("\n\n")[1]
    plain = human_quote_text(RFQ, OPTION, "Please quote air freight to DFW.", today=TODAY)
    assert "hope" not in plain.lower() and "address" not in plain


def test_port_to_port_dg_and_a_past_ready_date():
    rfq = {**RFQ, "pickup": None, "dangerous_goods": True, "ready_date": "2026-11-01", "contact_name": None}
    text = human_quote_text(rfq, {**OPTION, "transit_days": 3.2, "pickup": None}, None, "Please send the MSDS.", TODAY)
    assert text.startswith("Hi,") and "collect" not in text and "4 days in transit" in text
    assert "leaves on 22 November" in text and "MSDS" in text and "including air freight" in text
    assert gate.MONEY.findall(text) == ["6,175.48"]


def test_off_by_default_and_any_error_keeps_the_classic_wording(monkeypatch):
    classic = templates.quote_text(RFQ, OPTION)
    assert "All-in price: EUR 6,175.48" in classic and "Lena Hartmann" not in classic
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "human")
    assert "Lena Hartmann" in templates.quote_text(RFQ, OPTION, "Hello")
    assert "Lena Hartmann" not in templates.quote_text({**RFQ, "language": "de"}, OPTION)  # English only

    def broken(*a, **k):
        raise KeyError("carrier")
    monkeypatch.setattr(quote_style, "human_quote_text", broken)
    assert templates.quote_text(RFQ, OPTION) == classic


def test_the_quote_gate_finds_one_amount_and_puts_its_sentences_before_the_price():
    text = human_quote_text(RFQ, OPTION, None, today=TODAY)
    verdict = {"sentences": ["Your goods need temperature control, which this flight offers."], "chosen": OPTION}
    out, findings = gate.finish(text, verdict, RFQ)
    assert findings == [] and out.index("temperature") < out.index("The all-in price")


def test_a_town_without_postcode_is_named_and_a_placeholder_is_not():
    bonn = human_quote_text({**RFQ, "pickup": {"address": "Bonn, Germany", "zone": "53"}}, OPTION, None, today=TODAY)
    assert "we collect them in Bonn on 29 November" in bonn
    unknown = {**RFQ, "pickup": {"address": "customer warehouse (address not given)", "zone": None}}
    assert "we collect them on 29 November" in human_quote_text(unknown, OPTION, None, today=TODAY)
