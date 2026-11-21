"""Follow-up traps (after test_next_traps_15.py): rate desk when the portal is down, airline offload mails after a
booking, foreign / out-of-zone pickups, status questions in more languages, sanctioned destinations, "same as last
time", "end of next week" and the customer's register (Sie/du, vous, usted). Fakes only: no 5U, no gateway, no LLM.
Run: cd agent && uv run pytest -q test_next_traps_15b.py
"""

import threading
import time

import pytest

import extract as extract_mod
import rfq_agent
from bids import BidBoard
from inbox import FixtureMailbox

RAW = {"origin": "FRA", "destination": "LAX", "ask": "cheapest", "pickup_address": None, "ready_date": "2026-11-25",
       "pieces": [{"count": 1, "length": 120, "width": 80, "height": 100, "weight": 300, "weight_is_total": True}],
       "dim_unit": "cm", "weight_unit": "kg", "volume_unit": "m3", "volume": None, "commodity": "machine parts",
       "dangerous_goods": False, "customer_reference": None, "language": "en"}
MAIL = {"id": "m1", "thread_id": "t1", "from": "buyer@customer.example", "subject": "RFQ FRA-LAX",
        "body": "1 crate 120x80x100 cm, 300 kg, FRA to LAX, ready 25 Nov. Best price please."}
CARRIERS = [{"name": "Gannet Airways", "email": "gannet-airways@hackloop.mail", "kind": "airline", "serves": ["LAX"]},
            {"name": "Meridian Freightways", "email": "meridian-freightways@hackloop.mail", "kind": "airline",
             "serves": ["LAX"]}]
DOWN = "No price for FRA-LAX; portal: rates GN: 503 {\"detail\":\"Rates are unavailable: ask ratedesk@hackloop.mail\"}"


class Api:
    """Fake backend: answers /api/price from a list (one result per call)."""

    def __init__(self, results):
        self.results, self.prices, self.events, self.updates = list(results), [], [], []

    def create_session(self, customer, thread_id, received_at=None):
        return 1

    def session(self, session_id):
        return {"paused": False, "needs_human": "needs_human" in [k for k, _ in self.events], "quote": None}

    def update(self, session_id, **fields):
        self.updates.append(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append((kind, text))

    def price(self, rfq, bids=None, fallback=False):
        self.prices.append(list(bids or []))
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def _option(carrier, total, source="carrier_bid"):
    return {"source": source, "leg": "air", "carrier": carrier, "rate_id": "R-9", "currency": "EUR", "total": total,
            "transit_days": 3, "chargeable_weight_kg": 334, "breakdown": []}


def _run(tmp_path, monkeypatch, results, desk_body, carriers=CARRIERS):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    monkeypatch.setattr(rfq_agent, "RATEDESK_WAIT_SECONDS", 2)
    monkeypatch.setattr(rfq_agent, "RATEDESK_MIN_WAIT", 0.5)
    box, api, board = FixtureMailbox(tmp_path), Api(results), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(MAIL, box, api, board, carriers, 0.3), daemon=True)
    worker.start()
    give_up = time.time() + 4
    while not any(m["to"] == "ratedesk@hackloop.mail" for m in box.sent) and time.time() < give_up:
        time.sleep(0.02)
    desk = [m for m in box.sent if m["to"] == "ratedesk@hackloop.mail"]
    if desk and desk_body:
        board.deliver({"thread_id": desk[0]["thread_id"], "body": desk_body})
    worker.join(timeout=8)
    return box, api, desk


# ---- 1. rate desk when the portal is down ---------------------------------------------------------------------------

def test_portal_down_asks_the_rate_desk_once_and_quotes_its_rate(tmp_path, monkeypatch):
    priced = {"options": [_option("Gannet Airways", 980.0)], "chosen": _option("Gannet Airways", 980.0), "why": "ok"}
    box, api, desk = _run(tmp_path, monkeypatch, [{"options": [], "chosen": None, "why": DOWN}, priced],
                          "Rate for FRA-LAX, 300 kg: Gannet Airways\nTotal: 980.00 EUR\nTransit: 3 days\nRate ID: R-9")
    assert len(desk) == 1 and "FRA" in desk[0]["subject"]
    assert [b["carrier"] for b in api.prices[-1]] == ["Gannet Airways"]  # the airline the desk named, not "Rate desk"
    assert box.sent[-1]["thread_id"] == "t1" and "980.00" in box.sent[-1]["body"]


def test_the_portal_working_never_mails_the_rate_desk(tmp_path, monkeypatch):
    priced = {"options": [_option("Gannet Airways", 980.0, "portal")], "chosen": _option("Gannet Airways", 980.0,
                                                                                         "portal"), "why": "ok"}
    box, api, desk = _run(tmp_path, monkeypatch, [priced], None)
    assert desk == [] and box.sent[-1]["thread_id"] == "t1"


def test_a_silent_rate_desk_still_quotes_the_sheet_price_in_time(tmp_path, monkeypatch):
    sheet = {"options": [_option("Wayzata", 1100.0, "sheet")], "chosen": _option("Wayzata", 1100.0, "sheet"),
             "why": "cheapest: Wayzata (sheet); portal: rates GN: 503 unavailable"}
    started = time.time()
    box, api, desk = _run(tmp_path, monkeypatch, [sheet], None)
    assert len(desk) == 1 and time.time() - started < 6
    assert box.sent[-1]["thread_id"] == "t1" and "1,100.00" in box.sent[-1]["body"]


def test_ratedesk_off_is_the_old_path(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq_agent, "RATEDESK", False)
    sheet = {"options": [_option("Wayzata", 1100.0, "sheet")], "chosen": _option("Wayzata", 1100.0, "sheet"),
             "why": "portal: rates GN: 503 unavailable"}
    box, api, desk = _run(tmp_path, monkeypatch, [sheet], None)
    assert desk == []


def test_desk_targets_add_a_carrier_address_the_portal_names():
    why = "portal: rates GN: 503 price this lane by email with gannet-airways@hackloop.mail or ratedesk@hackloop.mail"
    got = rfq_agent.desk_targets(why, CARRIERS, asked=set())
    assert [t["email"] for t in got] == ["gannet-airways@hackloop.mail", "ratedesk@hackloop.mail"]
    assert rfq_agent.desk_targets(why, CARRIERS, asked={"gannet-airways@hackloop.mail"})[0]["name"] == "Rate desk"
    assert rfq_agent.desk_targets("portal: evil@attacker.example 503", CARRIERS, set())[0]["email"] == \
        "ratedesk@hackloop.mail"  # never an address outside the allowed list


def test_desk_airline_only_when_exactly_one_is_named():
    names = [c["name"] for c in CARRIERS]
    assert rfq_agent.desk_airline("Gannet Airways can do it", names) == "Gannet Airways"
    assert rfq_agent.desk_airline("Gannet Airways or Meridian Freightways", names) is None


# ---- 2. currencies: bids in any listed currency, the quote in the one asked ------------------------------------------

import gate  # noqa: E402
from bids import parse_bid  # noqa: E402


@pytest.mark.parametrize("body, total, currency", [
    ("Total: 1 234,50 EUR\nTransit: 2 days", 1234.5, "EUR"),       # space thousands (was read as 234.50)
    ("Total: 12 400.00 EUR\nTransit: 2 days", 12400.0, "EUR"),  # no-break space
    ("Total: R$ 5.000,00\nTransit: 2 days", 5000.0, "BRL"),        # was USD
    ("Total: £980.00\nTransit: 2 days", 980.0, "GBP"),
    ("Total: PLN 4.500,00\nTransit: 2 days", 4500.0, "PLN"),
    ("Total: 4.500,00 zł\nTransit: 2 days", 4500.0, "PLN"),
    ("Total: 9800 SEK\nTransit: 2 days", 9800.0, "SEK"),
    ("Total: CHF 1'234.00\nTransit: 2 days", 1234.0, "CHF"),
    ("Total: US$ 1,100.00\nTransit: 2 days", 1100.0, "USD"),
    ("Total: 1.234,50 €\nTransit: 2 days", 1234.5, "EUR"),
])
def test_bid_amounts_in_any_listed_currency(body, total, currency):
    bid = parse_bid(body, 300)
    assert (bid["total"], bid["currency"]) == (total, currency)


def test_option_2_450_eur_is_no_space_thousands_amount():
    assert parse_bid("Option 2 450 EUR all-in\nTransit: 2 days", 300)["total"] == 450.0


def test_we_try_is_no_turkish_lira():
    assert parse_bid("We try our best. Total: EUR 900.00\nTransit: 2 days", 300)["currency"] == "EUR"


OPTION_EUR = {"source": "sheet", "carrier": "Kestrel Airways", "rate_id": None, "currency": "EUR", "total": 2350.0,
              "total_eur": 2350.0, "transit_days": 5, "breakdown": []}
FX = {"USD": 0.86, "CHF": 1.07, "GBP": 1.15, "PLN": 0.235, "SEK": 0.091, "CAD": 0.62, "JPY": 0.0057}


@pytest.mark.parametrize("body, code", [
    ("Please quote in PLN.", "PLN"), ("Could you price this in Canadian dollars?", "CAD"),
    ("Quotation in SEK please.", "SEK"), ("Please quote in zloty.", "PLN"), ("please quote in yen", "JPY"),
])
def test_the_quote_is_written_in_any_currency_with_a_rate(body, code):
    verdict = gate.review({"ask": "cheapest", "ready_date": "2026-11-25", "pieces": [], "language": "en"},
                          {"options": [OPTION_EUR], "chosen": OPTION_EUR, "fx": FX}, {"subject": "RFQ", "body": body})
    assert verdict["chosen"]["currency"] == code and not verdict["hold"]
    assert verdict["chosen"]["total"] == round(2350.0 / FX[code], 2) and verdict["chosen"]["total_eur"] == 2350.0


def test_a_currency_without_a_rate_is_held_not_guessed():
    verdict = gate.review({"ask": "cheapest", "ready_date": "2026-11-25", "pieces": [], "language": "en"},
                          {"options": [OPTION_EUR], "chosen": OPTION_EUR, "fx": {"USD": 0.86}},
                          {"subject": "RFQ", "body": "Please quote in KRW."})
    assert verdict["hold"] and verdict["chosen"]["currency"] == "EUR"


def test_a_polish_goods_value_does_not_hold_the_quote():
    verdict = gate.review({"ask": "cheapest", "ready_date": "2026-11-25", "pieces": [], "language": "en"},
                          {"options": [OPTION_EUR], "chosen": OPTION_EUR, "fx": FX},
                          {"subject": "RFQ", "body": "3 pallets, invoice value in PLN 40,000, FRA to GRU."})
    assert not verdict["hold"] and verdict["chosen"]["currency"] == "EUR"
