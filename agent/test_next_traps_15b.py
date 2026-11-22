"""Follow-up traps (after test_next_traps_15.py): rate desk when the portal is down, currencies, share links that
fail and upload asks, airline offload mails after a booking, foreign / out-of-zone pickups, status questions in more
languages, sanctioned destinations, "end of next week" and a bid in documents.zip. Fakes only: no 5U, no gateway, no LLM.
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
    monkeypatch.setattr(rfq_agent, "PORTAL_RETRY_LAST_SECONDS", 0)  # the rate desk alone (test_portal_retry.py)
    monkeypatch.setattr(rfq_agent, "RATEDESK_UNTIL", 0)  # the 45 s desk wait these tests were written for
    box, api, board = FixtureMailbox(tmp_path), Api(results), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(MAIL, box, api, board, carriers, 0.3), daemon=True)
    worker.start()
    give_up = time.time() + 4
    while worker.is_alive() and not any(m["to"] == "ratedesk@hackloop.mail" for m in box.sent) \
            and time.time() < give_up:
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


def test_r93_portal_down_waits_longer_and_asks_the_silent_airlines_again(tmp_path, monkeypatch):
    """R93 too_low: portal 503, airlines silent at the cut-off, desk silent for 45 s → quoted 2 of 4 airlines' prices.
    Now the silent airlines get the request again and the round waits (until RATEDESK_UNTIL) for their price."""
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    monkeypatch.setattr(rfq_agent, "RATEDESK_WAIT_SECONDS", 0.5)
    monkeypatch.setattr(rfq_agent, "RATEDESK_MIN_WAIT", 0.2)
    monkeypatch.setattr(rfq_agent, "RATEDESK_UNTIL", 4)  # seconds after the RFQ in this test
    sheet = {"options": [_option("Wayzata", 1100.0, "sheet")], "chosen": _option("Wayzata", 1100.0, "sheet"),
             "why": "fastest: Wayzata (sheet); portal: rates GN: 503 unavailable"}
    full = {"options": [_option("Gannet Airways", 1460.0)], "chosen": _option("Gannet Airways", 1460.0), "why": "ok"}
    box, api, board = FixtureMailbox(tmp_path), Api([sheet, full]), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(MAIL, box, api, board, CARRIERS, 0.3), daemon=True)
    worker.start()
    give_up = time.time() + 3
    while time.time() < give_up and len([m for m in box.sent if m["to"] == "gannet-airways@hackloop.mail"]) < 2:
        time.sleep(0.02)
    again = [m for m in box.sent if m["to"] == "gannet-airways@hackloop.mail"]
    assert len(again) == 2  # asked in the bid round, silent, asked again with the rate desk
    board.deliver({"thread_id": again[-1]["thread_id"],
                   "body": "Rate FRA-LAX 300 kg\nTotal: 1460.00 EUR\nTransit: 1 day\nRate ID: R-GN1"})
    worker.join(timeout=8)
    assert [b["carrier"] for b in api.prices[-1]] == ["Gannet Airways"]
    assert box.sent[-1]["thread_id"] == "t1" and "1,460.00" in box.sent[-1]["body"]


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


# ---- 3. cloud links instead of attachments (links.py reads them; here: the ask when they fail, upload asks) ---------

import cloud_links  # noqa: E402
import links  # noqa: E402


def test_share_links_are_told_from_other_links():
    body = ("Details: https://www.dropbox.com/s/abc123/packing.xlsx?dl=0, our site https://www.acme.de and "
            "https://drive.google.com.evil.example/file/d/Y and https://acme.sharepoint.com/:x:/s/log/EAbc")
    assert cloud_links.find(body) == ["https://www.dropbox.com/s/abc123/packing.xlsx?dl=0",
                                      "https://acme.sharepoint.com/:x:/s/log/EAbc"]


@pytest.mark.parametrize("url, want", [
    ("https://acme.sharepoint.com/:x:/s/log/EAbc?e=1", "https://acme.sharepoint.com/:x:/s/log/EAbc?e=1&download=1"),
    ("https://onedrive.live.com/redir?resid=ABC", "https://onedrive.live.com/redir?resid=ABC&download=1"),
    ("https://drive.google.com/file/d/1FiLeId_x/view?usp=sharing", "https://drive.google.com/uc?export=download&id=1FiLeId_x"),
])
def test_share_links_become_direct_downloads(url, want):
    assert links.direct(url) == want


MISSING = {**RAW, "origin": None, "destination": None,
           "pieces": [{"count": None, "length": None, "width": None, "height": None, "weight": None,
                       "weight_is_total": False}]}
LINK_MAIL = {"id": "m7", "thread_id": "t7", "from": "buyer@customer.example", "subject": "RFQ",
             "body": "Hi, all details are in our Drive: https://drive.google.com/file/d/1F/view?usp=sharing\nThanks, Anna"}


def test_a_share_link_behind_a_login_gets_the_written_details_ask_in_the_first_minute(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (MISSING, 0.0001))
    monkeypatch.setattr(links, "read_all", lambda text, to_text, *a, **k: [(LINK_MAIL["body"].split()[-3], "",
                                                                             "not opened: a login page")])
    box, api = FixtureMailbox(tmp_path), Api([{"options": [], "chosen": None, "why": ""}])
    started = time.time()
    rfq_agent.handle_rfq(LINK_MAIL, box, api, BidBoard(), CARRIERS, 0.2)
    [ask] = box.sent
    assert ask["thread_id"] == "t7" and "can't open the link" in ask["body"] and "attach the file" in ask["body"]
    assert time.time() - started < 5


def test_a_company_website_link_alone_is_no_reason_to_ask(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (MISSING, 0.0001))
    monkeypatch.setattr(links, "read_all", lambda text, to_text, *a, **k: [])
    box, api = FixtureMailbox(tmp_path), Api([{"options": [], "chosen": None, "why": ""}])
    rfq_agent.handle_rfq({**LINK_MAIL, "body": "Hi, please quote. www.acme.de"}, box, api, BidBoard(), CARRIERS, 0.2)
    assert box.sent == []  # a person, as before


def test_cloud_links_off_finds_nothing(monkeypatch):
    monkeypatch.setattr(cloud_links, "CLOUD_LINKS", False)
    assert cloud_links.find(LINK_MAIL["body"]) == []


@pytest.mark.parametrize("text, asks", [
    ("Please upload the quote to our Dropbox folder.", True),
    ("Kindly save your offer in our SharePoint.", True),
    ("Bitte laden Sie das Angebot in unseren Ordner hoch.", True),
    ("The packing list is in our Drive: https://drive.google.com/file/d/1F/view", False),
    ("Please quote FRA-LAX.", False),
])
def test_upload_asks(text, asks):
    assert cloud_links.asks_upload(text) is asks


def test_an_upload_ask_gets_the_quote_in_the_body_and_attached_with_one_line(tmp_path):
    class Box(FixtureMailbox):
        def reply(self, mail, body, subject=None, attachments=None):
            self.attached = attachments
            return super().reply(mail, body, subject)
    box = Box(tmp_path)
    option = {"carrier": "Gannet Airways", "currency": "EUR", "total": 980.0, "transit_days": 3}
    mail = {**MAIL, "body": "1 crate FRA-LAX 300 kg. Please upload the quote to our Dropbox folder."}
    text = "Hi,\n\nGannet Airways can fly it for EUR 980.00 all in.\n\nThanks,\nLena"
    rfq_agent._reply_quote(box, mail, text, {"origin": "FRA", "destination": "LAX", "pieces": []}, option, "S-1")
    body = box.sent[-1]["body"]
    assert "EUR 980.00" in body and cloud_links.UPLOAD_NOTE in body and body.rstrip().endswith("Lena")
    assert box.attached


# ---- 4. airline mails after the booking: offload, rebooking, delay --------------------------------------------------

import booking_agent  # noqa: E402
import main  # noqa: E402
from router import route  # noqa: E402

SESSION = {"id": 3, "thread_id": "t3", "customer": "buyer@customer.example", "paused": False, "status_updates": [],
           "rfq": {"origin": "FRA", "destination": "LAX", "contact_name": "Anna Berg"},
           "booking": {"booking_reference": "BK-AB12CD34", "airline": "Gannet Airways", "status": "confirmed"}}


class CrmApi:
    def __init__(self, session=SESSION):
        self.session_, self.updates, self.events = dict(session), [], []

    def find(self, thread_id=None, reference=None):
        return self.session_ if reference == "BK-AB12CD34" else None

    def update(self, session_id, **fields):
        self.updates.append(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append((kind, text))


AIRLINES = {"gannet-airways@hackloop.mail"}


@pytest.mark.parametrize("subject, body, events, eta", [
    ("Booking BK-AB12CD34 offloaded", "Your shipment was offloaded due to capacity and rebooked on the next flight. "
     "New ETA 27 Nov.", ["offloaded", "rebooked"], "27 Nov"),
    ("Re: Booking BK-AB12CD34", "Flight GN401 delayed by 24 hours, expected arrival 2026-11-28.", ["delayed"],
     "2026-11-28"),
    ("Status BK-AB12CD34", "Sendung wurde nicht verladen, umgebucht auf den nächsten Flug. Neue Ankunft 28.11.",
     ["offloaded", "rebooked"], "28.11."),
    ("BK-AB12CD34 departed", "Your cargo departed FRA at 14:05.", ["departed"], None),
])
def test_airline_updates_are_read_by_rules(subject, body, events, eta):
    assert route({"from": "gannet-airways@hackloop.mail", "subject": subject, "body": body, "attachments": []},
                 AIRLINES, known_thread=False) == "booking_update"
    assert booking_agent.airline_update(f"{subject}\n{body}") == (events, eta)


def test_an_offload_is_recorded_and_the_customer_gets_a_short_note(tmp_path):
    box, api = FixtureMailbox(tmp_path), CrmApi()
    mail = {"id": "a1", "thread_id": "a1", "from": "gannet-airways@hackloop.mail", "subject": "Booking BK-AB12CD34",
            "body": "Shipment offloaded, rebooked on next flight GN403. New ETA 27 Nov."}
    assert booking_agent.handle_booking_update(mail, box, api)
    [note] = box.sent
    assert note["thread_id"] == "t3" and note["body"].startswith("Hi Anna,")
    assert "offloaded" in note["body"] and "27 Nov" in note["body"] and "GN403" not in note["body"]
    assert not any(ch.isdigit() and "EUR" in note["body"] for ch in note["body"])  # no amount, ever
    [update] = api.updates
    assert "offloaded" in update["status_updates"][-1]["text"] and "27 Nov" in update["status_updates"][-1]["text"]


def test_a_departure_is_recorded_without_mailing_the_customer(tmp_path):
    box, api = FixtureMailbox(tmp_path), CrmApi()
    mail = {"id": "a2", "thread_id": "a2", "from": "gannet-airways@hackloop.mail", "subject": "BK-AB12CD34 departed",
            "body": "Departed FRA 14:05."}
    assert booking_agent.handle_booking_update(mail, box, api) and box.sent == []
    assert "departed" in api.updates[-1]["status_updates"][-1]["text"]


def test_the_tracking_answer_then_names_the_airline_update(tmp_path):
    from templates import tracking_text
    session = {**SESSION, "quote": {"transit_days": 3},
               "status_updates": [{"at": "x", "text": "Booking BK-AB12CD34: it was offloaded from the planned flight"}]}
    assert "offloaded" in tracking_text(session)


def test_a_bid_without_a_booking_reference_still_routes_as_a_bid():
    assert route({"from": "gannet-airways@hackloop.mail", "subject": "Re: Rate request", "body": "Total: EUR 900",
                  "attachments": []}, AIRLINES, known_thread=True) == "carrier_bid"


def test_airline_updates_off_routes_as_before(monkeypatch):
    import router
    monkeypatch.setattr(router, "AIRLINE_UPDATES", False)
    assert route({"from": "gannet-airways@hackloop.mail", "subject": "BK-AB12CD34 offloaded", "body": "",
                  "attachments": []}, AIRLINES, known_thread=False) == "other"


def test_dispatch_hands_the_update_to_the_crm(tmp_path):
    box, api = FixtureMailbox(tmp_path), CrmApi()
    mail = {"id": "a3", "thread_id": "a3", "from": "gannet-airways@hackloop.mail", "to": "leylu@hackloop.mail",
            "subject": "Booking BK-AB12CD34 delayed", "body": "Delayed 24 h.", "attachments": []}
    main.dispatch(mail, box, api, BidBoard(), [{"name": "Gannet Airways", "email": "gannet-airways@hackloop.mail",
                                                "kind": "airline", "serves": ["LAX"]}])
    assert box.sent and "delayed" in box.sent[-1]["body"]


# ---- 5. pickups outside our 32 zones ---------------------------------------------------------------------------------

import carriers as carriers_mod  # noqa: E402
import extract  # noqa: E402


@pytest.mark.parametrize("address, zone, airport", [
    ("Industriestr. 5, 6020 Innsbruck, Austria", "80", "MUC"),
    ("Werkstr. 3, A-4020 Linz", "80", "MUC"),
    ("Bahnhofstr. 1, CH-8001 Zürich", "70", "STR"),
    ("Gewerbestrasse 7, 4057 Basel, Schweiz", "70", "STR"),
    ("Keizersgracht 1, 1015 CN Amsterdam", "40", "DUS"),
    ("Havenweg 2, Rotterdam, Netherlands", "40", "DUS"),
    ("Alexanderplatz 1, 10178 Berlin", "20", "HAM"),
    ("Messeallee 1, 04356 Leipzig", "36", "FRA"),
    ("Frankenstr. 1, 90461 Nürnberg", "93", "MUC"),
    ("Hauptstr. 1, 60311 Frankfurt", "60", "FRA"),   # a zone of ours stays itself
])
def test_pickups_outside_the_zones_get_the_nearest_zone(address, zone, airport):
    assert carriers_mod.pickup_zone({"address": address, "zone": None}) == zone
    assert extract.zone_airport({"address": address}) == airport


@pytest.mark.parametrize("address", ["Rue 5, 75001 Paris, France", "Via Roma 1, 20121 Milano, Italy",
                                     "Unit 4, 1234 Somewhere"])
def test_other_countries_are_never_guessed(address):
    assert carriers_mod.nearest_zone(address) is None
    assert extract.zone_airport({"address": address}) is None


def test_to_rfq_sets_the_nearest_zone_for_the_backend_and_notes_it():
    raw = {**RAW, "origin": None, "pickup_address": "Industriestr. 5, 6020 Innsbruck, Austria"}
    rfq, missing = extract.to_rfq(raw)
    assert rfq["pickup"]["zone"] == "80" and rfq["origin"] == "MUC" and "origin" not in missing
    assert "Austria" in rfq["airport_note"]


def test_the_nearest_zones_truckers_are_asked():
    kit = carriers_mod.load_carriers()
    rfq = {"destination": "LAX", "pickup": {"address": "6020 Innsbruck, Austria", "zone": None}}
    truckers = [c for c in carriers_mod.carriers_for(kit, rfq) if c["kind"] == "trucker"]
    assert truckers and all("80" in c["serves"] for c in truckers)


def test_foreign_pickup_off_is_as_before(monkeypatch):
    monkeypatch.setattr(carriers_mod, "FOREIGN_PICKUP", False)
    assert carriers_mod.pickup_zone({"address": "6020 Innsbruck, Austria", "zone": None}) is None
    assert carriers_mod.pickup_zone({"address": "10178 Berlin", "zone": None}) == "10"


def test_every_nearest_zone_is_a_real_zone():
    zones = carriers_mod.known_zones()
    assert set(carriers_mod.NEAREST.values()) <= zones and not set(carriers_mod.NEAREST) & zones
    assert {z for _, z, _ in carriers_mod.COUNTRY_ZONE} <= zones


# ---- 6. status questions in more languages ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Bonjour, où en est mon envoi ?", "Où est la marchandise ?", "Des nouvelles de l'expédition ?",
    "¿Dónde está mi envío?", "Hola, ¿hay novedades de la carga?", "¿Ya ha salido el pedido?",
    "A che punto è la spedizione?", "Dov'è la merce?", "La spedizione è già partita?",
    "Waar blijft mijn zending?", "Is de lading al vertrokken?", "Onde está a minha carga?", "Kargom nerede?",
    "Gönderinin durumu nedir?",
])
def test_status_questions_in_more_languages(text):
    assert booking_agent.is_status_question(text)


@pytest.mark.parametrize("text", [
    "Où est la facture ?", "¿Dónde está la factura?", "Annulez l'envoi s'il vous plaît.", "Dov'è il prezzo finale?",
    "Fatura nerede?", "Can you change the delivery address?", "Merci pour la réservation !",
])
def test_other_questions_still_go_to_a_person(text):
    assert not booking_agent.is_status_question(text)


def test_status_langs_off_is_en_de_only(monkeypatch):
    monkeypatch.setattr(booking_agent, "STATUS_LANGS", False)
    assert not booking_agent.is_status_question("¿Dónde está mi envío?")


# ---- 7. sanctioned destinations: a polite decline, no price ---------------------------------------------------------

import sanctions  # noqa: E402


@pytest.mark.parametrize("destination, body", [
    ("SVO", "2 pallets FRA to SVO, 400 kg."),
    ("Moscow", "2 pallets to Moscow, 400 kg."),
    ("IKA", "Air freight to Tehran please."),
    ("DXB", "Ship to DXB, final destination: Tehran, Iran."),
    ("DXB", "Goods to Dubai for re-export to Russia."),
    ("FNJ", "Pyongyang, 100 kg."),
    ("LAX", "Lieferung nach Minsk über Los Angeles."),
])
def test_sanctioned_destinations(destination, body):
    assert sanctions.sanctioned({"destination": destination}, {"subject": "RFQ", "body": body})


@pytest.mark.parametrize("destination, body", [
    ("JFK", "2 crates of Russian dolls to New York."),
    ("ORD", "We used to ship to Moscow, this one goes to Chicago."),
    ("LAX", "Our supplier has a branch in Moscow, but this goes to Los Angeles."),
    ("DXB", "3 pallets to Dubai. Not to Iran."),
    ("SIN", "Kazakhstan-born engineer, shipment to Singapore."),
    ("DEL", "Persian rugs, 2 pieces, to Delhi."),
    ("ORD", "Please deliver to Syria Street 12, Chicago."),
    ("DTW", "Ship to ACME, 5 Syria Street, Detroit."),
    ("ORD", "Ship FRA to ORD. Please send the invoice to our Moscow office."),
    ("ORD", "Ship part IRN-4471 to Chicago, 2 pcs 40 kg."),
    ("ORD", "Quote FRA to ORD please.\n--\nACME LLC, offices in Germany, Russia and China"),
])
def test_ordinary_mentions_are_no_sanction(destination, body):
    assert sanctions.sanctioned({"destination": destination}, {"subject": "RFQ", "body": body}) is None


def test_a_sanctioned_rfq_gets_the_decline_and_no_carrier_mail(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**RAW, "destination": "SVO"}, 0.0001))
    box, api = FixtureMailbox(tmp_path), Api([{"options": [], "chosen": None, "why": ""}])
    rfq_agent.handle_rfq({**MAIL, "body": "1 crate 300 kg FRA to Moscow SVO"}, box, api, BidBoard(), CARRIERS, 0.2)
    [decline] = box.sent
    assert decline["thread_id"] == "t1" and "sanctions" in decline["body"] and "EUR" not in decline["body"]
    assert api.prices == [] and api.updates[-1]["stage"] == "done"


def test_the_decline_is_german_for_a_german_mail():
    assert sanctions.decline_text("Moskau", "de").startswith("Guten Tag")


def test_sanctions_off(monkeypatch):
    monkeypatch.setattr(sanctions, "SANCTIONS", False)
    assert sanctions.sanctioned({"destination": "SVO"}, {"body": ""}) is None


# ---- 9. relative deadlines ---------------------------------------------------------------------------------------------

from datetime import date  # noqa: E402

SAT, MON_READY = date(2026, 11, 21), date(2026, 11, 23)


@pytest.mark.parametrize("text, sent, by", [
    ("has to be there by end of next week", date(2026, 11, 18), date(2026, 11, 27)),  # Wed → next week's Friday
    ("has to be there by end of next week", SAT, date(2026, 11, 27)),                # weekend → the coming Friday
    ("must arrive by the end of this week", date(2026, 11, 24), date(2026, 11, 27)),
    ("Die Ware muss bis Ende nächster Woche ankommen.", date(2026, 11, 18), date(2026, 11, 27)),
    ("needed in Chicago by the end of the month", SAT, date(2026, 11, 30)),
    ("muss bis Monatsende da sein", SAT, date(2026, 11, 30)),
    ("must be delivered within 3 working days", SAT, date(2026, 11, 26)),           # Mon ready + 3 business days
    ("Lieferung innerhalb von 5 Werktagen", SAT, date(2026, 11, 30)),
    ("has to arrive within a week", SAT, date(2026, 11, 30)),
    ("must arrive by 2026-11-28, ideally by end of next week", SAT, date(2026, 11, 28)),  # a written date wins
])
def test_relative_deadlines(text, sent, by):
    assert gate.deadline(text, MON_READY, sent) == by


@pytest.mark.parametrize("text", ["Please send your quote within 2 days.", "We ship every week.",
                                  "Transit time within 5 days is fine?", "Ready end of next week.",
                                  "Goods are ready in 2 days.", "Pickup within 3 working days."])
def test_no_relative_deadline(text):
    assert gate.deadline(text, MON_READY, SAT) is None


def test_relative_deadline_narrows_the_options():
    fast = {**OPTION_EUR, "carrier": "Fast", "total": 2900.0, "transit_days": 2}
    slow = {**OPTION_EUR, "carrier": "Slow", "total": 2100.0, "transit_days": 9}
    verdict = gate.review({"ask": "cheapest", "ready_date": "2026-11-23", "pieces": [], "language": "en"},
                          {"options": [fast, slow], "chosen": slow, "fx": FX},
                          {"subject": "RFQ", "body": "Must arrive by end of next week.",
                           "received_at": "2026-11-18T10:00:00+00:00"})
    assert verdict["chosen"]["carrier"] == "Fast"


def test_relative_deadline_off(monkeypatch):
    monkeypatch.setattr(gate, "RELATIVE_DEADLINE", False)
    assert gate.deadline("has to be there by end of next week", MON_READY, SAT) is None


# ---- 10. a bid in documents.zip ("Please see attached.") ------------------------------------------------------------

class _ZipBox:
    def __init__(self, text):
        self.text = text

    def attachment(self, mail, attachment):
        return self.text.encode()


class _TextApi:
    def attachment_text(self, name, content):
        import base64 as b64
        return b64.b64decode(content).decode()


def test_a_bid_in_documents_zip_behind_a_bare_pointer_is_read():
    from bids import read_bid
    reply = {"body": "Hello,\n\nplease see attached.\n\nBest regards\nHansekogge Trucking",
             "attachments": [{"id": 1, "filename": "documents.zip"}]}
    text = rfq_agent._with_attachments(reply, _ZipBox("Total: 245.10 EUR\nTransit: 1 day\nRate ID: TRK-1"), _TextApi())
    bid, _ = read_bid(text, 300.0)
    assert bid["total"] == 245.10 and bid["rate_id"] == "TRK-1"


@pytest.mark.parametrize("body, name, content", [
    ("Please see the attached brochure.", "documents.zip", "Total: 245.10 EUR"),            # brochure word
    ("Please see attached.", "terms-and-conditions.pdf", "Handling fee: EUR 45.00"),        # T&C file
    ("Please see attached. Price is EUR 900.", "documents.zip", "Total: 245.10 EUR"),       # amount in the mail
    ("Please see attached.", "documents.zip", "Our company profile and history"),           # no total inside
    ("Please see attached.", "scan.pdf", "COMMERCIAL INVOICE\nAmount due: EUR 980.00"),      # invoice inside
])
def test_neutral_files_never_become_a_bid_otherwise(body, name, content):
    reply = {"body": body, "attachments": [{"id": 1, "filename": name}]}
    assert rfq_agent._with_attachments(reply, _ZipBox(content), _TextApi()) == body


def test_bid_neutral_files_off(monkeypatch):
    monkeypatch.setattr(rfq_agent, "BID_NEUTRAL_FILES", False)
    reply = {"body": "Please see attached.", "attachments": [{"id": 1, "filename": "documents.zip"}]}
    assert rfq_agent._with_attachments(reply, _ZipBox("Total: 245.10 EUR"), _TextApi()) == "Please see attached."


# ---- review of #213 ---------------------------------------------------------------------------------------------------

def test_an_amount_is_never_read_as_the_new_eta():
    assert booking_agent.airline_update("BK-AB12CD34 offloaded. Storage charges expected: EUR 12.50") == (["offloaded"],
                                                                                                         None)
    assert booking_agent.airline_update("Rebooked, expected costs 1.250") == (["rebooked"], None)
    assert booking_agent.airline_update("Delayed, new ETA 27.11.2026")[1] == "27.11.2026"


def test_a_customer_cannot_fake_an_airline_update():
    mail = {"from": "anna@acme.example", "subject": "BK-AB12CD34 offloaded", "body": "It was offloaded!", "attachments": []}
    assert route(mail, AIRLINES, known_thread=True) == "customer_reply"


def test_a_lower_case_dollar_prefix_is_no_singapore_dollar():
    import bids
    assert [(a["value"], a["currency"]) for a in bids._amounts("pallets$500")] == [(500.0, "USD")]
    assert [(a["value"], a["currency"]) for a in bids._amounts("Total: 1 234,50 EUR")] == [(1234.5, "EUR")]
    assert [(a["value"], a["currency"]) for a in bids._amounts("S$ 1,200.00 all-in")] == [(1200.0, "SGD")]


@pytest.mark.parametrize("body", ["Please deliver to our Moscow warehouse.", "Final destination: our Minsk plant.",
                                  "Goods go to our Tehran branch, 2 pcs 40 kg."])
def test_a_warehouse_plant_or_branch_there_is_still_a_sanctioned_destination(body):
    assert sanctions.sanctioned({"destination": "IST"}, {"subject": "RFQ", "body": body})
