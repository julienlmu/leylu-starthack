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


# ---- 3. cloud links instead of attachments ---------------------------------------------------------------------------

import httpx  # noqa: E402

import cloud_links  # noqa: E402


def test_find_takes_https_links_on_allowlisted_hosts_only():
    body = ("Details here: https://www.dropbox.com/s/abc123/packing.xlsx?dl=0. Also http://drive.google.com/file/d/X/view "
            "and https://evil.example/drive.google.com/x and https://drive.google.com.evil.example/file/d/Y and "
            "https://docs.google.com/spreadsheets/d/1AbC/edit#gid=7")
    assert cloud_links.find(body) == ["https://www.dropbox.com/s/abc123/packing.xlsx?dl=0",
                                      "https://docs.google.com/spreadsheets/d/1AbC/edit#gid=7"]


@pytest.mark.parametrize("url, want", [
    ("https://www.dropbox.com/s/abc123/packing.xlsx?dl=0", "https://www.dropbox.com/s/abc123/packing.xlsx?dl=1"),
    ("https://www.dropbox.com/scl/fi/xyz/rfq.pdf?rlkey=k1&dl=0", "https://www.dropbox.com/scl/fi/xyz/rfq.pdf?rlkey=k1&dl=1"),
    ("https://drive.google.com/file/d/1FiLeId_x/view?usp=sharing", "https://drive.google.com/uc?export=download&id=1FiLeId_x"),
    ("https://drive.google.com/open?id=1FiLeId", "https://drive.google.com/uc?export=download&id=1FiLeId"),
    ("https://docs.google.com/document/d/1Doc/edit", "https://docs.google.com/document/d/1Doc/export?format=pdf"),
    ("https://docs.google.com/spreadsheets/d/1AbC/edit#gid=7",
     "https://docs.google.com/spreadsheets/d/1AbC/export?format=csv&gid=7"),
    ("https://acme.sharepoint.com/:x:/s/log/EAbc?e=1", "https://acme.sharepoint.com/:x:/s/log/EAbc?e=1&download=1"),
])
def test_share_links_become_direct_downloads(url, want):
    assert cloud_links.direct(url) == want


def _transport(routes):
    def handler(request):
        assert "cookie" not in {k.lower() for k in request.headers}  # never a cookie or credential
        assert "authorization" not in {k.lower() for k in request.headers}
        return routes(request)
    return httpx.MockTransport(handler)


def test_fetch_follows_an_allowed_redirect_and_names_the_file():
    def routes(request):
        if request.url.host == "drive.google.com":
            return httpx.Response(303, headers={"location": "https://drive.usercontent.google.com/download?id=1F",
                                                "set-cookie": "NID=1; Domain=.google.com"})
        return httpx.Response(200, content=b"pieces,weight\n2,450 kg\n",
                              headers={"content-type": "text/csv", "content-disposition": 'attachment; filename="pl.csv"'})
    name, data = cloud_links.fetch("https://drive.google.com/file/d/1F/view", _transport(routes))
    assert name == "pl.csv" and data.startswith(b"pieces")


@pytest.mark.parametrize("response, why", [
    (httpx.Response(302, headers={"location": "https://login.evil.example/x"}), "not an allowed"),
    (httpx.Response(302, headers={"location": "http://dl.dropboxusercontent.com/x"}), "not an allowed"),
    (httpx.Response(200, content=b"<html>Sign in</html>", headers={"content-type": "text/html"}), "web page"),
    (httpx.Response(403), "login"),
    (httpx.Response(200, content=b"x", headers={"content-type": "application/pdf",
                                                 "content-length": str(11 * 1024 * 1024)}), "10 MB"),
    (httpx.Response(404), "HTTP 404"),
])
def test_fetch_refuses_logins_pages_big_files_and_other_hosts(response, why):
    with pytest.raises(cloud_links.LinkError, match=why):
        cloud_links.fetch("https://www.dropbox.com/s/a/b.pdf?dl=0", _transport(lambda request: response))


MISSING = {**RAW, "origin": None, "destination": None,
           "pieces": [{"count": None, "length": None, "width": None, "height": None, "weight": None,
                       "weight_is_total": False}]}
LINK_MAIL = {"id": "m7", "thread_id": "t7", "from": "buyer@customer.example", "subject": "RFQ",
             "body": "Hi, all details are in our Drive: https://drive.google.com/file/d/1F/view?usp=sharing\nThanks, Anna"}


class LinkApi(Api):
    def __init__(self):
        super().__init__([{"options": [], "chosen": None, "why": ""}])
        self.read_texts = []

    def attachment_text(self, filename, content_base64, password_hints=None):
        import base64 as b64
        self.read_texts.append((filename, b64.b64decode(content_base64)))
        return "Pieces: 2 crates 120x80x100 cm, 450 kg total, FRA to LAX"


def test_a_link_behind_a_login_gets_the_written_details_ask_in_the_first_minute(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (MISSING, 0.0001))

    def fail(url, transport=None):
        raise cloud_links.LinkError("needs a login")
    monkeypatch.setattr(cloud_links, "fetch", fail)
    box, api = FixtureMailbox(tmp_path), LinkApi()
    started = time.time()
    rfq_agent.handle_rfq(LINK_MAIL, box, api, BidBoard(), CARRIERS, 0.2)
    [ask] = box.sent
    assert ask["thread_id"] == "t7" and "can't open the link" in ask["body"] and "attach the file" in ask["body"]
    assert time.time() - started < 5
    assert any("Shared link not opened" in text for _, text in api.events)


def test_a_readable_link_is_read_like_an_attachment(tmp_path, monkeypatch):
    seen = []

    def extract(mail, model=None):
        seen.append(mail["body"])
        return (RAW if "--- Attachment" in mail["body"] else MISSING), 0.0001
    monkeypatch.setattr(extract_mod, "extract", extract)
    monkeypatch.setattr(cloud_links, "fetch", lambda url, transport=None: ("packing.pdf", b"%PDF-1.4 ..."))
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)
    box, api = FixtureMailbox(tmp_path), LinkApi()
    rfq_agent.handle_rfq(LINK_MAIL, box, api, BidBoard(), [], 0.2)
    assert api.read_texts == [("packing.pdf", b"%PDF-1.4 ...")]
    assert any("450 kg total" in body for body in seen)  # the link's text reached the extraction
    assert any("Shared link read: packing.pdf" in text for _, text in api.events)


def test_cloud_links_off_ignores_the_link(monkeypatch):
    monkeypatch.setattr(cloud_links, "CLOUD_LINKS", False)
    assert cloud_links.find(LINK_MAIL["body"]) == []


@pytest.mark.parametrize("text, asks", [
    ("Please upload the quote to our Dropbox folder.", True),
    ("Kindly save your offer in our SharePoint.", True),
    ("Bitte das Angebot in unseren Ordner hochladen.", False),  # German verb at the end: no match needed for now
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
    assert box.attached and box.attached[0]["filename"].endswith(".pdf")


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
