"""Tracking sweep: tracking questions in the many ways people (and 5U's tracking agent) write them, through the real
code paths: main.dispatch → router → tracking_agent / booking_agent → the real backend client → the real FastAPI app
and its SQLite CRM (crm.find, GET /api/sessions).

Nothing reaches 5U: mails go to a FixtureMailbox, the backend is started KEYLESS by this module (no portal, no
gateway, no phone push) on a free local port (never 8000), and no LLM is called (the tracking path must stay free).
Every test starts from the same CRM: eight sessions of seven customers, five customers booked (Kowalski twice), one
quote not booked, one booking still waiting for the airline's reference.

Each test asserts what a careful forwarder answers: the right booking, or a polite question for the booking
reference (no invented status). Never another customer's booking. xfail(strict=True) = a gap we can't close safely
with rules (reason says why). Run: cd agent && uv run pytest -q test_tracking_sweep.py -rxX
"""

import itertools
import os
import socket
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx
import pytest

import booking_agent
import main
import tracking_agent
import tracking_match
from backend import Backend
from bids import BidBoard
from booking_agent import handle_customer_reply
from inbox import FixtureMailbox
from router import route
from tracking_agent import handle_tracking

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
IDS = itertools.count(70000)
XF = lambda reason: pytest.mark.xfail(strict=True, reason=reason)  # noqa: E731
TRACKING = "tracking@hackloop.mail"
ASKS = "starts with BK-"  # tracking_unknown_text: we ask for the booking reference


def _rfq(origin, destination, ready, pieces, pickup=None, ref=None, contact=None):
    return {"origin": origin, "destination": destination, "ask": "cheapest", "ready_date": ready,
            "pickup": {"address": pickup, "zone": pickup[:2]} if pickup else None,
            "pieces": [{"count": c, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": w}
                       for c, w in pieces],
            "volume_m3": None, "commodity": "general cargo", "dangerous_goods": False, "customer_reference": ref,
            "language": "en", "contact_name": contact}


def _quote(carrier, rate_id, total, days):
    return {"source": "portal", "leg": "air", "carrier": carrier, "rate_id": rate_id, "currency": "EUR",
            "total": total, "transit_days": days, "valid_until": "2026-11-30"}


def _booking(ref, airline, rate_id, status="booked", **extra):
    return {"booking_reference": ref, "airline": airline, "rate_id": rate_id, "status": status, **extra}


# Session ids follow this order (the CRM is emptied before every test): sonnberg = S-1, auer = S-2, ...
SEEDS = {
    "sonnberg": dict(customer="sonnberg-roesterei@hackloop.mail", thread=425,
                     rfq=_rfq("FRA", "JFK", "2026-11-25", [(6, 205.5)], pickup="61018 Bad Homburg, Germany",
                              ref="PO-4711", contact="Anna Sonnberg"),
                     quote=_quote("Solace Air Cargo", "R-zTsJ8k2Q", 9876.0, 1),
                     booking=_booking("BK-50NN8E8G", "Solace Air Cargo", "R-zTsJ8k2Q", "confirmed", weight_kg=1233.0)),
    "auer": dict(customer="auer-maschinenbau@hackloop.mail", thread=512,
                 rfq=_rfq("DUS", "JFK", "2026-11-27", [(4, 385.0)], ref="4500123456", contact="Thomas Auer"),
                 quote=_quote("Kestrel Airways", "R-CEOKa1b2", 4321.0, 2),
                 booking=_booking("BK-UHRIJQ2L", "Kestrel Airways", "R-CEOKa1b2")),
    "lindqvist": dict(customer="lindqvist-medtech@hackloop.mail", thread=640,
                      rfq=_rfq("FRA", "JFK", "2026-11-25", [(12, 56.33)], pickup="51447 Bergisch Gladbach, Germany",
                               contact="Sara Lindqvist"),
                      quote=_quote("Solace Air Cargo", "R-OdES9x8y", 3100.0, 1),
                      booking=_booking("BK-LQ7M2X9P", "Solace Air Cargo", "R-OdES9x8y", "confirmed")),
    "meyer": dict(customer="meyer-industrie@hackloop.mail", thread=733,
                  rfq=_rfq("MUC", "PVG", "2026-11-26", [(2, 450.0)], ref="ORD-2024-118", contact="Klaus Meyer"),
                  quote=_quote("Aurelia Air Cargo", "R-E7-Aq1w2", 3900.0, 3),
                  booking=_booking("BK-MY3K8Q1Z", "Aurelia Air Cargo", "R-E7-Aq1w2")),
    "kowalski_gru": dict(customer="kowalski-trade@hackloop.mail", thread=811,
                         rfq=_rfq("STR", "GRU", "2026-11-24", [(3, 238.333333)], contact="Jan Kowalski"),
                         quote=_quote("Kestrel Airways", "R-KwGr1234", 4800.0, 4),
                         booking=_booking("BK-KW1A2B3C", "Kestrel Airways", "R-KwGr1234")),
    "kowalski_dxb": dict(customer="kowalski-trade@hackloop.mail", thread=812,
                         rfq=_rfq("HAM", "DXB", "2026-11-28", [(1, 320.0)], contact="Jan Kowalski"),
                         quote=_quote("Meridian Freightways", "R-KwDx5678", 1500.0, 2),
                         booking=_booking("BK-KW9X8Y7Z", "Meridian Freightways", "R-KwDx5678", "confirmed")),
    "huber": dict(customer="huber-optik@hackloop.mail", thread=905, stage="quoted",  # quoted, never booked
                  rfq=_rfq("FRA", "ORD", "2026-11-26", [(1, 250.0)], ref="PO-9001", contact="Eva Huber"),
                  quote=_quote("Kestrel Airways", "R-Hub9001x", 1100.0, 2), booking=None),
    "nordwind": dict(customer="nordwind-moebel@hackloop.mail", thread=960,  # booked by email, no reference yet
                     rfq=_rfq("STR", "MIA", "2026-11-27", [(2, 300.0)], contact="Ole Nordwind"),
                     quote=_quote("Meridian Freightways", None, 2100.0, 3),
                     booking={"pending_email": "meridian-freightways@hackloop.mail", "airline": "Meridian Freightways",
                              "status": "requested by email"}),
}
ALL_BK = {s["booking"]["booking_reference"] for s in SEEDS.values() if (s["booking"] or {}).get("booking_reference")}


# ---- harness -------------------------------------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def backend(tmp_path_factory):
    """The real backend, keyless (no portal, no 5U, no ntfy), own DB, on a free port that is never 8000."""
    tmp = tmp_path_factory.mktemp("tracking-backend")
    port = int(os.environ.get("TRACKING_SWEEP_PORT") or _free_port())
    assert port != 8000, "never the live backend's port"
    env = {**os.environ, "FIVEU_API_KEY": "", "NTFY_TOPIC": "", "DB_PATH": str(tmp / "crm.sqlite3"),
           "FX_FILE": str(tmp / "fx.json")}
    proc = subprocess.Popen(["uv", "run", "-q", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port),
                             "--log-level", "warning"], cwd=BACKEND_DIR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.skip("local backend did not start")
    yield url, tmp / "crm.sqlite3"
    proc.terminate()
    proc.wait(10)


def _seed(api: Backend, customer, thread, rfq, quote=None, booking=None, stage="booked") -> dict:
    sid = api.create_session(customer, thread)
    if booking and booking.get("booking_reference"):
        booking = {**booking, "team_reference": f"S-{sid}"}  # what backend/booking.py sends to the portal
    api.update(sid, stage=stage, outcome="won" if stage == "booked" else "open", rfq=rfq, quote=quote, booking=booking)
    return api.session(sid)


@pytest.fixture
def crm(backend):
    """The backend client on a CRM that holds exactly SEEDS (emptied first, so ids start at 1 again)."""
    url, db = backend
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM sessions")
        c.execute("DELETE FROM events")
        c.execute("DELETE FROM sqlite_sequence")
    api = Backend(url)
    api.seeded = {name: _seed(api, **spec) for name, spec in SEEDS.items()}
    return api


@pytest.fixture
def started(monkeypatch):
    """main._start runs the tracking and reply handlers in this thread; the RFQ agent (LLM) is only recorded."""
    names = []

    def start(handler, *args):
        names.append(handler.__name__)
        if handler in (handle_tracking, handle_customer_reply):
            handler(*args)

    monkeypatch.setattr(main, "_start", start)
    return names


def ask(api, body, subject="Shipment status", sender=TRACKING, thread=None) -> list[dict]:
    """Delivers one mail through main.dispatch (real routing); returns what we sent."""
    n = next(IDS)
    mail = {"id": n, "thread_id": thread or n, "from": sender, "to": "leylu@hackloop.mail", "subject": subject,
            "body": body, "attachments": [], "received_at": None}
    box = FixtureMailbox("unused")
    main.dispatch(mail, box, api, BidBoard(), [])
    return box.sent


def answers(sent: list[dict], *names: str) -> None:
    """Exactly one mail, naming the bookings of `names` and no other customer's booking."""
    assert len(sent) == 1, sent
    body = sent[0]["body"]
    want = {SEEDS[n]["booking"]["booking_reference"] for n in names}
    assert all(ref in body for ref in want), body
    assert not any(ref in body for ref in ALL_BK - want), body
    assert ASKS not in body or len(names) > 1, body


def asks(sent: list[dict]) -> None:
    """Exactly one mail: we ask for the booking reference and state no booking or status at all."""
    assert len(sent) == 1, sent
    body = sent[0]["body"]
    assert ASKS in body and not any(ref in body for ref in ALL_BK), body
    assert "confirmed by the airline" not in body and "waiting for the airline" not in body, body


# ---- 1. references typed every way --------------------------------------------------------------------------------

REFERENCES = [
    ("Where is shipment BK-50NN8E8G right now?", "sonnberg"),  # as written in our booking mail
    ("Hi, status of bk-50nn8e8g please?", "sonnberg"),  # lower case
    ("Could you check booking Bk-50nN8e8G for us?", "sonnberg"),  # mixed case
    ("Where is BK50NN8E8G?", "sonnberg"),  # no dash
    ("Where is BK 50NN8E8G?", "sonnberg"),  # space
    ("Status of BK–50NN8E8G?", "sonnberg"),  # en dash from a word processor
    ("Where is BK-50NN8E9G?", "sonnberg"),  # one wrong character
    ("Where is BK-5ONN8E8G?", "sonnberg"),  # letter O for the zero
    ("Where is BK-50NN8EG?", "sonnberg"),  # one character missing
    ("Where is BK-05NN8E8G?", "sonnberg"),  # two characters swapped
    ("Where is BK-UHRIJQ2I?", "auer"),  # I for L
    ("Status for rate R-zTsJ8k2Q please", "sonnberg"),  # the rate ID we booked
    ("Status for rate id r-ztsj8k2q please", "sonnberg"),  # rate ID in lower case
    ("What is the status of S-1?", "sonnberg"),  # our portal team reference
    ("What is the status of our ref s-1?", "sonnberg"),
    ("Our reference S-0002: where is it?", "auer"),
    ("Where is our PO-4711?", "sonnberg"),  # the customer's reference as in the RFQ
    ("Where is our shipment for PO 4711?", "sonnberg"),
    ("Where is PO4711?", "sonnberg"),
    ("where is po#4711?", "sonnberg"),
    ("Status of P.O. 4711 please", "sonnberg"),
    ("Where is PO-0004711?", "sonnberg"),  # leading zeros added
    ("Status of PO no. 4711?", "sonnberg"),
    ("Where is purchase order 4711?", "sonnberg"),
    ("Our order number is 4711, where is it?", "sonnberg"),
    ("Wo bleibt die Sendung zur Bestellnummer 4711?", "sonnberg"),
    ("Wo ist PO-Nr. 4711?", "sonnberg"),
    ("Where is PO 4500123456?", "auer"),  # SAP PO, stored without a label
    ("Where is 4500123456?", "auer"),  # a long PO number on its own
    ("Where is PO-4500123456?", "auer"),
    ("Where is order ORD-2024-118?", "meyer"),
    ("where is ord-2024-118?", "meyer"),
    ("Where is ORD2024118?", "meyer"),
]


@pytest.mark.parametrize("body, who", REFERENCES)
def test_a_reference_typed_any_way_finds_the_booking(body, who, crm, started):
    answers(ask(crm, body), who)


def test_the_answer_is_logged_on_the_right_session(crm, started):
    answers(ask(crm, "Where is our shipment for PO 4711?"), "sonnberg")
    events = crm.http.get(f"/api/sessions/{crm.seeded['sonnberg']['id']}/events").json()
    [event] = [e for e in events if e["kind"] == "tracking_answer"]
    assert event["data"]["to"] == TRACKING and "BK-50NN8E8G" in event["data"]["body"]
    assert "customer reference" in event["text"]


# ---- 2. no reference: the shipment's details (5U's own format and variants) ----------------------------------------

DETAILS = [
    ("could you please tell me the current status of our shipment: Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, "
     "1233 kg, ready on 2026-11-25? Where is it now?", "sonnberg"),  # the real #923
    ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1.233 kg, ready on 2026-11-25", "sonnberg"),
    ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1,233.00 kg, ready on 2026-11-25", "sonnberg"),
    ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1.233,00 kg, ready on 2026-11-25", "sonnberg"),
    ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233kg, ready on 2026-11-25", "sonnberg"),
    ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 2718 lbs, ready on 25.11.2026", "sonnberg"),
    ("Sonnberg Kaffeeroesterei GmbH, Frankfurt to New York, ready on 25 November 2026", "sonnberg"),
    ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, ready on November 25, 2026", "sonnberg"),
    ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, ready on 11/25/2026", "sonnberg"),
    ("Auer Maschinenbau GmbH, DUS to JFK, 1540 kg, ready on 2026-11-27? Where is it now?", "auer"),  # #1212
    ("Auer Maschinenbau GmbH, Düsseldorf to New York, 1.540 kg, ready on 27.11.2026", "auer"),
    ("Lindqvist MedTech AB, 51447 to JFK, 676 kg, ready on 25 Nov 2026", "lindqvist"),
    ("Meyer Industrie GmbH, MUC to PVG, 900 kg, ready on 2026-11-26", "meyer"),
    ("Kowalski Trade, STR to GRU, 715 kg, ready on 2026-11-24", "kowalski_gru"),
    ("Kowalski Trade, HAM to DXB, 320 kg, ready on 2026-11-28", "kowalski_dxb"),
    ("Kowalski Trade, 320 kg: status please?", "kowalski_dxb"),
    ("Hallo, wo befindet sich unsere Luftfracht? Abholung in 61018 am 25.11.2026, 1.233 kg nach New York.", "sonnberg"),
    ("Wo ist unsere Sendung? Sonnberg Kaffeerösterei GmbH, 61018 nach JFK, 1.233 kg, bereit am 25.11.2026", "sonnberg"),
    # the words "BK reference" are no unknown booking number: the details still count
    ("I don't have the BK reference at hand: Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, ready on "
     "2026-11-25", "sonnberg"),
    # a date that isn't written as the ready date (when it was booked) contradicts nothing
    ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, booked on 21 Nov 2026: where is it?", "sonnberg"),
    # the airline named with its legal form is not another customer
    ("Our shipment with Solace Air Cargo Ltd: 61018 to JFK, 1233 kg, ready on 2026-11-25", "sonnberg"),
]


@pytest.mark.parametrize("body, who", DETAILS)
def test_the_shipment_is_found_by_its_details(body, who, crm, started):
    answers(ask(crm, body, subject="Status of our shipment"), who)


# ---- 3. only the company, the signature or the contact -------------------------------------------------------------

COMPANY = [
    ("Hello, this is Anna from Sonnberg Roesterei. Where is our air freight shipment to New York right now?", "sonnberg"),
    ("Hi, where is our shipment?\n\nKind regards\nAnna Sonnberg\nHead of Purchasing\nSonnberg Kaffeeroesterei GmbH",
     "sonnberg"),
    ("Where is our shipment? Best, Anna Sonnberg", "sonnberg"),  # the contact's full name
    ("Sonnberg Kaffeerösterei GmbH: where is our air freight?", "sonnberg"),
    ("Wo ist unsere Sendung?\n\nMit freundlichen Grüßen\nAnna Sonnberg\nSonnberg Kaffeerösterei GmbH", "sonnberg"),
    ("Auer Maschinenbau here. Where is our shipment right now?", "auer"),
    ("Status please.\n\nThomas Auer\nAuer Maschinenbau GmbH", "auer"),
    ("MEYER INDUSTRIE GMBH - WHERE IS OUR CARGO?", "meyer"),
    ("Lindqvist MedTech: any news on our shipment?", "lindqvist"),
    ("Kowalski Trade here: where is our shipment to Dubai?", "kowalski_dxb"),  # two bookings: the city tells them apart
    ("Kowalski Trade here: where is our shipment to São Paulo?", "kowalski_gru"),
    ("Jan Kowalski here, where is the one from Hamburg?", "kowalski_dxb"),
    ("Kowalski Trade: where is our 715 kg shipment?", "kowalski_gru"),
]


@pytest.mark.parametrize("body, who", COMPANY)
def test_a_question_that_only_names_the_company_gets_that_customers_booking(body, who, crm, started):
    answers(ask(crm, body), who)


def test_two_bookings_of_one_customer_are_both_answered_never_guessed(crm, started):
    answers(ask(crm, "Kowalski Trade here, where is our shipment?"), "kowalski_gru", "kowalski_dxb")
    answers(ask(crm, "Hello, any update on our air freight?\n\nBest regards\nJan Kowalski"), "kowalski_gru", "kowalski_dxb")


def test_more_bookings_of_one_customer_than_we_list_are_asked_for(crm, started):
    for n, (dest, kg) in enumerate((("JFK", 500.0), ("ORD", 610.0))):
        _seed(crm, "kowalski-trade@hackloop.mail", 820 + n, _rfq("STR", dest, "2026-11-29", [(1, kg)]),
              _quote("Kestrel Airways", f"R-KwX{n}0000", 2000.0, 3),
              _booking(f"BK-KWX{n}0000", "Kestrel Airways", f"R-KwX{n}0000"))
    [sent] = ask(crm, "Kowalski Trade here, where is our shipment?")
    assert ASKS in sent["body"] and "BK-KW1A2B3C" not in sent["body"]
    # a detail still picks one of the four
    answers(ask(crm, "Kowalski Trade here, where is our shipment to Dubai?"), "kowalski_dxb")


# ---- 4. the question arrives in a thread ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", ["Hi Lena, where is our shipment now?", "Any update on our shipment?",
                                  "Wo ist unsere Sendung gerade?", "Has it left yet?"])
def test_a_status_question_in_the_booked_quote_thread_is_answered_from_the_crm(body, crm, started):
    sonnberg = crm.seeded["sonnberg"]
    sent = ask(crm, body, subject="Re: Your air freight booking", sender=sonnberg["customer"],
               thread=sonnberg["thread_id"])
    answers(sent, "sonnberg")
    assert sent[0]["thread_id"] == sonnberg["thread_id"] and sent[0]["to"] == sonnberg["customer"]
    assert started == ["handle_customer_reply"] and crm.session(sonnberg["id"])["needs_human"] is False


@pytest.mark.parametrize("body", ["Please cancel the booking.", "Where is it? And please send the invoice.",
                                  "Where is it? Can we change the delivery address?", "When will it be picked up?"])
def test_other_mails_in_the_booked_thread_still_go_to_a_person(body, crm, started):
    sonnberg = crm.seeded["sonnberg"]
    sent = ask(crm, body, subject="Re: Your air freight booking", sender=sonnberg["customer"],
               thread=sonnberg["thread_id"])
    assert sent == [] and crm.session(sonnberg["id"])["needs_human"] is True


def test_a_tracking_mail_in_a_customers_thread_gets_that_booking(crm, started):
    sonnberg = crm.seeded["sonnberg"]
    sent = ask(crm, "Where is it now?", subject="Re: Your air freight booking", thread=sonnberg["thread_id"])
    answers(sent, "sonnberg")
    # the details it names win over the thread it came in
    sent = ask(crm, "Auer Maschinenbau GmbH, DUS to JFK, 1540 kg, ready on 2026-11-27: where is it?",
               subject="Re: Your air freight booking", thread=sonnberg["thread_id"])
    answers(sent, "auer")
    answers(ask(crm, "Sonnberg Kaffeeroesterei here: any update?", subject="Re: booking", thread=sonnberg["thread_id"]),
            "sonnberg")
    # a thread that is no booking of ours: we ask
    asks(ask(crm, "Where is it now?", subject="Re: Status", thread=987654))
    # the thread only fills in for a question that names nothing: a name or a number may be someone else's
    for body in ("Huber Optik here, where is our shipment?", "What is the status of S-7?", "Where is 4711?",
                 "Hello, where is our shipment FRA to JFK, ready 2026-11-25?"):
        asks(ask(crm, body, subject="Re: Your air freight booking", thread=sonnberg["thread_id"]))


# ---- 5. forwarded mails: the reference only in the quoted history --------------------------------------------------

FORWARDED = [
    ("Could you check this one please?\n\n---------- Forwarded message ---------\nFrom: Anna Sonnberg "
     "<sonnberg-roesterei@hackloop.mail>\nDate: Sat, 21 Nov 2026 16:13\nSubject: shipment\n\n"
     "> Hello, where is PO 4711 now?", "sonnberg"),
    ("Status please, see below.\n\nOn Sat, 21 Nov 2026 at 16:40, Lena wrote:\n> Here's where booking BK-UHRIJQ2L "
     "stands (DUS to JFK with Kestrel Airways): booked.", "auer"),
    ("Please check the shipment of this customer.\n\n-----Original Message-----\nFrom: "
     "sonnberg-roesterei@hackloop.mail\nSent: Saturday, November 21, 2026 4:13 PM\nSubject: where is it\n\n"
     "Where is our shipment?", "sonnberg"),
    ("Fwd from our customer:\n> Lindqvist MedTech AB, 51447 to JFK, 676 kg, ready on 2026-11-25. Where is it?",
     "lindqvist"),
    ("Forwarding for our client.\n\n> Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, ready on 2026-11-25\n\n"
     "Best regards\nKlaus Meyer\nMeyer Industrie GmbH", "sonnberg"),
]


@pytest.mark.parametrize("body, who", FORWARDED)
def test_a_forwarded_question_is_read_with_its_quoted_history(body, who, crm, started):
    answers(ask(crm, body, subject="Fwd: shipment status"), who)


# ---- 6. never another customer's data: ask instead -----------------------------------------------------------------

ASK_INSTEAD = [
    "Where is booking BK-ZZ99ZZ99?",  # not ours
    "where is bk-zzzzzzzz?",
    # an unknown BK- number with Sonnberg's details: someone else's booking, not guessed from the details
    "bk-zzzzzzzz: Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, ready on 2026-11-25",
    "Where is PO 99887766?",  # a reference nobody has
    "Where is PO 9001?",  # Huber's quote, never booked: no invented status
    "What is the status of S-7?",  # the same quote by our reference
    "What is the status of S-8?",  # booked by email, the airline's reference hasn't come yet
    "Huber Optik here, where is our shipment?",
    "Nordwind Möbel here, where is our shipment?",
    "Meyer Optik GmbH, where is our shipment?",  # not Meyer Industrie
    "Sauerland Metall, where is our shipment to Shanghai?",  # not Auer
    "Hello, where is our shipment FRA to JFK, ready 2026-11-25?",  # Sonnberg's and Lindqvist's lane and day
    "Our shipment with Solace Air Cargo on 2026-11-25, where is it?",
    "Where is my shipment?",
    "Hi, this is Anna. Where is our shipment?",  # a first name names nobody
    "Meyer Industrie here: where is PO 4711?",  # Sonnberg's PO, Meyer's name: Meyer's reference is another one
    "Meyer Industrie: where is BK-50NN8E9G?",  # a typo of Sonnberg's booking, but Meyer asks
    "Sonnberg Roesterei: where is our 400 kg shipment?",  # not the 1233 kg we booked
    "Sonnberg Roesterei: where is our shipment to Tokyo?",  # we booked JFK
    "Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, ready on 2026-11-29",  # another ready date
    "Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, ready on 29.11.2026",  # the same, written German style
    "Where is 4711?",  # a bare short number is no reference (postcode? weight?)
    "Meyerhof GmbH, 900 kg to PVG: where is it?",  # Meyer Industrie's weight and lane, but not Meyer
    "Huber GmbH, DUS to JFK, 1540 kg, ready on 2026-11-27: where is it?",  # Auer's shipment exactly, Huber asks
    "Obermeyer Industrie, where is our shipment?",
]


@pytest.mark.parametrize("body", ASK_INSTEAD)
def test_unclear_or_foreign_questions_ask_for_the_reference(body, crm, started):
    asks(ask(crm, body))


def test_a_customer_with_a_booking_whose_reference_got_lost_is_asked(crm, started):
    """Sonnberg's second booking: the portal's answer got lost (pending_rate_id), 5U may have booked it anyway."""
    _seed(crm, "sonnberg-roesterei@hackloop.mail", 426, _rfq("FRA", "JFK", "2026-11-30", [(2, 400.0)]),
          _quote("Solace Air Cargo", "R-Lost0001", 2500.0, 1), {"pending_rate_id": "R-Lost0001"}, stage="quoted")
    asks(ask(crm, "Sonnberg Kaffeeroesterei GmbH here: where is our shipment?"))
    answers(ask(crm, DETAILS[0][0]), "sonnberg")  # the details still name the booked one


def test_a_typo_close_to_two_bookings_is_not_guessed(crm, started):
    for n, customer in enumerate(("alpha-pumpen@hackloop.mail", "beta-ventile@hackloop.mail")):
        _seed(crm, customer, 830 + n, _rfq("FRA", "JFK", "2026-11-30", [(1, 100.0 + n)]),
              _quote("Kestrel Airways", f"R-Ab{n}11111", 900.0, 2),
              _booking(f"BK-AAAA111{n + 1}", "Kestrel Airways", f"R-Ab{n}11111"))
    [sent] = ask(crm, "Where is BK-AAAA1113?")
    assert ASKS in sent["body"] and "BK-AAAA111" not in sent["body"]
    answers(ask(crm, "Where is BK-50NN8E9G?"), "sonnberg")  # still unique for Sonnberg


# ---- 7. a status question and a new request in one mail ------------------------------------------------------------

def test_tracking_mail_with_a_new_request_answers_the_status_only(crm, started):
    body = ("Where is BK-50NN8E8G? Also, we have a new shipment: 2 pallets, 400 kg, FRA to ORD, ready 2026-12-01, "
            "please send a quote.")
    answers(ask(crm, body), "sonnberg")
    answers(ask(crm, "Where is PO 4711? Also please quote a new one: 400 kg FRA to ORD, ready 2026-12-01."), "sonnberg")
    assert started == ["handle_tracking", "handle_tracking"] and len(crm.sessions()) == len(SEEDS)


def test_a_customers_new_mail_with_status_and_rfq_gets_the_quote_first(crm, started):
    """The first reply in a customer's thread must be the quote: no tracking answer goes out before it."""
    mail = {"id": 1, "thread_id": 1, "from": "sonnberg-roesterei@hackloop.mail", "subject": "New request + status",
            "body": "Where is BK-50NN8E8G? Also please quote 2 pallets, 400 kg, FRA to ORD, ready 2026-12-01."}
    assert route(mail, set(), known_thread=False) == "rfq"
    sent = ask(crm, mail["body"], subject=mail["subject"], sender=mail["from"])
    assert started == ["handle_rfq"] and sent == []


@XF("the router sends a mail to one agent: a customer's new mail that asks for a status and a new quote gets the "
    "quote (first reply must be it) but the status part is never answered; appending a tracking text to the quote "
    "risks the one-amount scorer, a second mail after the quote is untested")
def test_the_status_part_of_a_customers_rfq_mail_is_answered_too(crm, started):
    ask(crm, "Where is BK-50NN8E8G? Also please quote 2 pallets, 400 kg, FRA to ORD, ready 2026-12-01.",
        sender="sonnberg-roesterei@hackloop.mail")
    assert "handle_tracking" in started


# ---- 8. known gaps (not safe with rules) ---------------------------------------------------------------------------

@XF("one company word ('Sonnberg') is not enough: 'Meyer Optik' would then get Meyer Industrie's booking. We need "
    "the full company name, the contact's full name or the address")
def test_one_word_of_the_company_name(crm, started):
    answers(ask(crm, "Hi, Anna from Sonnberg here. Where is our shipment?"), "sonnberg")


@XF("two wrong characters in a BK- number are too far to tell a typo from another team's booking: we ask")
def test_a_booking_reference_with_two_typos(crm, started):
    answers(ask(crm, "Where is BK-50NN8F9G?"), "sonnberg")


@XF("the commodity alone ('our coffee') is not stored as a match signal; reading it needs the RFQ text or an LLM")
def test_the_shipment_named_by_its_goods_only(crm, started):
    answers(ask(crm, "Where is our coffee shipment to New York?"), "sonnberg")


# ---- 9. kill switches: off restores the behaviour before the sweep -------------------------------------------------

def _flags(monkeypatch, *, fuzzy=True, formats=True, customer=True, in_thread=True):
    monkeypatch.setattr(tracking_match, "FUZZY", fuzzy)
    monkeypatch.setattr(tracking_match, "FORMATS", formats)
    monkeypatch.setattr(tracking_match, "CUSTOMER", customer)
    monkeypatch.setattr(tracking_agent, "IN_THREAD", in_thread)
    monkeypatch.setattr(booking_agent, "TRACKING_IN_THREAD", in_thread)


def test_all_switches_off_restore_the_old_answers(crm, started, monkeypatch):
    _flags(monkeypatch, fuzzy=False, formats=False, customer=False, in_thread=False)
    for body in ("Where is our shipment for PO 4711?", "Hi, status of bk-50nn8e8g please?",
                 "Where is BK-50NN8E9G?", "Status for rate R-zTsJ8k2Q please",
                 "Hello, this is Anna from Sonnberg Roesterei. Where is our air freight shipment to New York right now?",
                 "Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1.233,00 kg, ready on 2026-11-25",
                 "Where is BK-ZZ99ZZ99?"):
        asks(ask(crm, body))
    answers(ask(crm, "Where is shipment BK-50NN8E8G right now?"), "sonnberg")  # exact references as before
    answers(ask(crm, DETAILS[0][0]), "sonnberg")  # the real #923 as before
    # the old rule: an unknown lower-case bk- reference didn't stop the details match
    answers(ask(crm, "bk-zzzzzzzz: Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, ready on 2026-11-25"), "sonnberg")
    sonnberg = crm.seeded["sonnberg"]
    asks(ask(crm, "Where is it now?", subject="Re: booking", thread=sonnberg["thread_id"]))
    assert ask(crm, "Where is our shipment now?", sender=sonnberg["customer"], thread=sonnberg["thread_id"]) == []
    assert crm.session(sonnberg["id"])["needs_human"] is True


@pytest.mark.parametrize("flag, body, old", [
    ("fuzzy", "Where is our shipment for PO 4711?", "ask"),
    ("fuzzy", "Hello, this is Anna from Sonnberg Roesterei. Where is our shipment to New York?", "answer"),
    ("customer", "Hello, this is Anna from Sonnberg Roesterei. Where is our shipment to New York?", "ask"),
    ("customer", "Where is our shipment for PO 4711?", "answer"),
    ("formats", "Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1.233,00 kg, ready on 2026-11-25", "ask"),
    ("formats", "Where is BK-50NN8E9G?", "answer"),
])
def test_each_switch_turns_off_only_its_own_part(flag, body, old, crm, started, monkeypatch):
    _flags(monkeypatch, **{flag: False})
    sent = ask(crm, body)
    asks(sent) if old == "ask" else answers(sent, "sonnberg")


def test_in_thread_switch_off_hands_the_status_question_to_a_person(crm, started, monkeypatch):
    _flags(monkeypatch, in_thread=False)
    sonnberg = crm.seeded["sonnberg"]
    assert ask(crm, "Where is our shipment now?", sender=sonnberg["customer"], thread=sonnberg["thread_id"]) == []
    assert crm.session(sonnberg["id"])["needs_human"] is True
    asks(ask(crm, "Where is it now?", subject="Re: booking", thread=sonnberg["thread_id"]))
