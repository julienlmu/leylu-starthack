"""RFQ shape sweep: the request shapes 5U is likely to send next, run through the real code paths with fakes.

Nothing reaches 5U: mails go to a FixtureMailbox, the extraction is a hand-written raw dict (what the model returns;
the "misread" cases are what a weaker read returns), pricing, sessions, attachment text and tariff ingestion go to
a local KEYLESS backend that this module starts on its own port (never 8000; no portal, no gateway, its own DB,
fx file and ingest folder). Every LLM call is refused.

Areas: 1 several shipments in one RFQ · 2 cheapest AND fastest · 3 corrections before our quote · 4 December ready
dates and tariff mails · 5 units · 6 Incoterms and door wording · 7 places.
Each test asserts what a careful forwarder does. xfail(strict=True) = it still breaks (the reason says how and why).
Run: cd agent && uv run pytest -q test_rfq_shape_sweep.py -rxX
"""

import base64
import itertools
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest

import amendments
import exclusions
import extract as extract_mod
import gate
import llm
import main
import rfq_agent
from backend import Backend
from bids import BidBoard
from carriers import KIT_LIST, load_carriers
from inbox import FixtureMailbox

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
KIT = BACKEND_DIR / "data" / "start-kit"
# Own port, never 8000 and never test_next_traps' NEXT_TRAPS_PORT: parallel runs set NEXT_TRAPS_PORT per machine user
PORT = int(os.environ.get("SHAPE_SWEEP_PORT") or int(os.environ.get("NEXT_TRAPS_PORT", "8737")) + 1000)
IDS = itertools.count(70000)
XF = lambda reason: pytest.mark.xfail(strict=True, reason=reason)  # noqa: E731


def piece(count=1, weight=None, total=True, length=None, width=None, height=None, volume=None, volume_total=True):
    return {"count": count, "length": length, "width": width, "height": height, "weight": weight,
            "weight_is_total": total, "volume": volume, "volume_is_total": volume_total}


def raw(**fields):
    """A raw extraction as the model returns it (numbers as written, units named)."""
    base = {"origin": "FRA", "destination": "ORD", "ask": "cheapest", "pickup_address": None,
            "ready_date": "2026-11-25", "pieces": [piece(3, 420)], "dim_unit": "cm", "weight_unit": "kg",
            "volume_unit": "m3", "volume": 1.8, "commodity": "machine parts", "dangerous_goods": False,
            "customer_reference": None, "language": "en"}
    return {**base, **fields}


def opt(carrier, total, days, source="sheet", rate_id=None):
    return {"source": source, "leg": "air", "carrier": carrier, "rate_id": rate_id, "currency": "EUR", "total": total,
            "transit_days": days, "valid_until": "2026-11-30", "chargeable_weight_kg": 420, "breakdown": []}


CANNED = {"options": [opt("Kestrel Airways", 2400.0, 5)], "chosen": opt("Kestrel Airways", 2400.0, 5), "why": "test"}
AIRLINES = [{"name": "Aurelia Air Cargo", "email": "aurelia@carrier.example", "kind": "airline", "serves": ["*"]},
            {"name": "Borealis Freight", "email": "borealis@carrier.example", "kind": "airline", "serves": ["*"]}]


# ---- harness -------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def backend_url(tmp_path_factory):
    """The real backend, keyless, own DB / fx file / ingest folder, on a port that is never 8000."""
    tmp = tmp_path_factory.mktemp("sweep-backend")
    env = {**os.environ, "FIVEU_API_KEY": "", "NTFY_TOPIC": "", "DB_PATH": str(tmp / "crm.sqlite3"),
           "FX_FILE": str(tmp / "fx.json"), "INGEST_DIR": str(tmp / "ingested")}
    proc = subprocess.Popen(["uv", "run", "-q", "uvicorn", "app:app", "--port", str(PORT), "--log-level", "warning"],
                            cwd=BACKEND_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{PORT}"
    for _ in range(150):
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.skip("local backend did not start")
    yield url
    proc.terminate()
    proc.wait(10)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No LLM call ever (the extraction is faked per test), no write to the real exclusions file, no parked mail
    from another test; held quotes and fallbacks go out at once."""
    def refuse(*args, **kwargs):
        raise AssertionError("the sweep never calls the LLM")
    monkeypatch.setattr(llm, "chat_json", refuse)
    monkeypatch.setattr(exclusions, "STORE", tmp_path / "exclusions.json")
    monkeypatch.setattr(rfq_agent, "GATE_AUTO_SEND_SECONDS", 0.0)
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: None)
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0.0)
    amendments._pending.clear()
    yield
    amendments._pending.clear()


class Api(Backend):
    """The real backend client. canned: a fixed /api/price answer; slow_create: the session appears late."""

    def __init__(self, url, canned=None, slow_create=0.0):
        super().__init__(url)
        self.canned, self.slow_create, self.priced, self.log = canned, slow_create, [], []

    def create_session(self, customer, thread_id, received_at=None):
        time.sleep(self.slow_create)
        return super().create_session(customer, thread_id, received_at)

    def price(self, rfq, bids=None, fallback=False):
        self.priced.append((json.loads(json.dumps(rfq)), list(bids or [])))
        return self.canned if self.canned is not None else super().price(rfq, bids, fallback)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.log.append((kind, text, data))
        return super().event(session_id, kind, text, data, cost)

    def kinds(self):
        return [k for k, _, _ in self.log]

    def texts(self):
        return [t for _, t, _ in self.log]

    def quote(self):
        return next((d["option"] for k, _, d in self.log if k == "quote_sent"), None)

    def held(self):
        return any(t.startswith("Quote held") for t in self.texts())

    def findings(self):
        return {f["code"] for k, t, d in self.log if t.startswith("Quote gate:") for f in (d or {}).get("findings", [])}


def mail(body, subject="Air freight request", received_at=None, sender="buyer@customer.example", thread_id=None,
         attachments=()):
    n = next(IDS)
    return {"id": n, "thread_id": thread_id or f"t{n}", "from": sender, "to": "leylu@hackloop.mail",
            "subject": subject, "body": body, "attachments": list(attachments), "received_at": received_at}


def fake_reads(monkeypatch, reads):
    """reads: one raw dict for every read, or a function mail -> raw (a correction is read again)."""
    read = reads if callable(reads) else (lambda m: reads)
    monkeypatch.setattr(extract_mod, "extract", lambda m, model=None: (json.loads(json.dumps(read(m))), 0.0001))


def run(monkeypatch, tmp_path, api, m, reads, carriers=(), replies=None, during=None, cutoff=3.0):
    """handle_rfq with fake reads. replies: {carrier name: [(delay s, body)]}; during(box, board): runs once the
    bid requests are out, before any reply (a customer's correction)."""
    fake_reads(monkeypatch, reads)
    box, board = FixtureMailbox(tmp_path), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(m, box, api, board, list(carriers), cutoff))
    worker.start()
    if carriers:
        give_up = time.time() + 5
        while "carrier_asked" not in api.kinds() and worker.is_alive() and time.time() < give_up:
            time.sleep(0.01)
    if during:
        during(box, board)
    if replies:
        deliver(box, board, carriers, replies)
    worker.join(timeout=30)
    return box, [s for s in box.sent if s["thread_id"] == m["thread_id"]]


def deliver(box, board, carriers, replies):
    by_name = {c["name"]: c for c in carriers}
    sends = {s["to"]: s["thread_id"] for s in box.sent}
    start = time.time()
    for delay, name, body in sorted((d, n, b) for n, items in replies.items() for d, b in items):
        time.sleep(max(0.0, start + delay - time.time()))
        board.deliver({"id": next(IDS), "thread_id": sends[by_name[name]["email"]], "from": by_name[name]["email"],
                       "subject": "Re: Rate request", "body": body})


def bid(total, days=3, rate="X-1"):
    return f"Total: {total:,.2f} EUR\nTransit: {days} days\nRate ID: {rate}"


def amounts(text):
    return gate.MONEY.findall(text)


def total_kg(rfq):
    return sum(p["count"] * p["weight_kg"] for p in rfq["pieces"])


def best(url, rfq, bids=()):
    """The backend's own answer for the request read correctly: the price a careful forwarder quotes."""
    return httpx.post(f"{url}/api/price", json={"rfq": rfq, "bids": list(bids)}, timeout=30).json()


def as_rfq(raw_extraction):
    return extract_mod.to_rfq(raw_extraction)[0]


def in_backend(code: str, payload=None):
    """Runs `code` in the backend's venv with JSON on stdin; returns the JSON it prints last."""
    env = {**os.environ, "FIVEU_API_KEY": "", "DB_PATH": ":memory:", "FX_FILE": "/nonexistent/fx.json"}
    out = subprocess.run(["uv", "run", "-q", "python", "-c", code], cwd=BACKEND_DIR, env=env,
                         input=json.dumps(payload), capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# ---- 1. several shipments in one RFQ -------------------------------------------------------------------------------
# One combined price for two shipments is wrong either way (two lanes, or two consignments that fly apart and are
# billed apart). Until we quote each one correctly, a person answers: no quote, never a combined one.

def lots(*items):
    return [piece(c, w, volume=v) for c, w, v in items]


TWO_LANES = ("Hi,\n\nwe have two shipments ready on 2026-11-24 at FRA, please quote each:\n"
             "Lot A: 3 pallets, 420 kg, 1.8 cbm to JFK\nLot B: 2 pallets, 300 kg, 1.2 cbm to ORD\n\nThanks,\nLaura Berger")


@pytest.mark.parametrize("body, reads", [
    (TWO_LANES, raw(destination="JFK", volume=None, pieces=lots((3, 420, 1.8), (2, 300, 1.2)))),
    (TWO_LANES, raw(destination="JFK", volume=1.8, pieces=lots((3, 420, None)))),  # only lot A read
    ("Hello,\n\nplease quote air freight from Frankfurt: 2 crates, 500 kg, 2.0 cbm to New York and 1 crate, "
     "250 kg, 1.1 cbm to Chicago. Ready 25.11.2026.\n\nBest regards,\nTom Fischer",
     raw(destination="JFK", volume=3.1, pieces=lots((2, 500, None), (1, 250, None)))),
    ("Guten Tag,\n\nbitte zwei Sendungen ab FRA anbieten:\nSendung 1: 2 Paletten, 300 kg, 1,2 cbm nach JFK\n"
     "Sendung 2: 1 Palette, 150 kg, 0,6 cbm nach ORD\nBereit am 25.11.2026.\n\nViele Grüße\nAnna Weber",
     raw(destination="JFK", volume=None, language="de", pieces=lots((2, 300, 1.2), (1, 150, 0.6)))),
], ids=["two-lanes-both-lots", "two-lanes-lot-a-only", "cities", "german"])
def test_two_destinations_are_never_quoted_as_one_price(body, reads, backend_url, monkeypatch, tmp_path):
    api = Api(backend_url, CANNED)
    _, quotes = run(monkeypatch, tmp_path, api, mail(body), reads)
    assert quotes == [] and "needs_human" in api.kinds()


TWO_CONSIGNMENTS = ("Hello,\n\nplease quote FRA to JFK for two separate consignments:\n"
                    "1) 2 pallets, 400 kg, 1.6 cbm, ready 24.11.2026\n2) 3 pallets, 650 kg, 2.4 cbm, ready 02.12.2026\n\n"
                    "Each one flies on its own.\n\nRegards,\nTom Fischer")


@pytest.mark.parametrize("body", [
    TWO_CONSIGNMENTS,
    "Hi,\n\nFRA to JFK: lot 1 is ready on 24.11.2026 (2 pallets, 400 kg, 1.6 cbm), lot 2 is ready on 02.12.2026 "
    "(3 pallets, 650 kg, 2.4 cbm). Please quote both lots separately.\n\nThanks,\nTom",
], ids=["separate-consignments", "two-ready-dates"])
def test_one_lane_with_two_consignments_is_not_quoted_combined(body, backend_url, monkeypatch, tmp_path):
    reads = raw(destination="JFK", ready_date="2026-11-24", volume=None, pieces=lots((2, 400, 1.6), (3, 650, 2.4)))
    api = Api(backend_url, CANNED)
    _, quotes = run(monkeypatch, tmp_path, api, mail(body), reads)
    assert quotes == [] and "needs_human" in api.kinds()


@pytest.mark.parametrize("body", [
    "Hi,\n\nLot 1: 730 kg, 1.68 cbm. Lot 2: 380 kg, 0.95 cbm. FRA to ORD, ready 2026-11-25. Please ship both lots "
    "together as one consignment under one AWB.\n\nThanks,\nAnna",
    "Hi,\n\nwe send about two shipments a month to ORD. This one: 3 pallets, 420 kg, 1.8 cbm, FRA to ORD, "
    "ready 2026-11-25.\n\nThanks,\nAnna",
    "Hi,\n\n3 pallets, 420 kg, 1.8 cbm from FRA to ORD, routing via JFK is fine. Ready 2026-11-25.\n\nThanks,\nAnna",
    "Hi,\n\nour last shipment to JFK went well, thanks. Now: 3 pallets, 420 kg, 1.8 cbm, FRA to ORD, "
    "ready 2026-11-25.\n\nThanks,\nAnna",
    "Hi,\n\ngoods available from 24.11.2026, ready for pickup 25.11.2026: 3 pallets, 140 kg each, 420 kg in total, "
    "1.8 cbm, FRA to ORD.\n\nThanks,\nAnna",
    "Hi,\n\nthis is one of two shipments this month: 3 pallets, 420 kg, 1.8 cbm, FRA to ORD, ready 2026-11-25.\n\n"
    "Thanks,\nAnna",
], ids=["lots-together", "shipments-a-month", "via", "earlier-shipment", "available-and-ready", "two-this-month"])
def test_one_shipment_that_mentions_more_is_still_quoted(body, backend_url, monkeypatch, tmp_path):
    reads = raw(volume=None, pieces=lots((1, 730, 1.68), (1, 380, 0.95))) if "Lot 1" in body else raw()
    _, quotes = run(monkeypatch, tmp_path, Api(backend_url, CANNED), mail(body), reads)
    assert len(quotes) == 1


# ---- 2. cheapest AND fastest -----------------------------------------------------------------------------------------
# The quote follows the ask the backend and the gate decide, states exactly one amount, and names the other option
# in words only (the gate's finish() holds a mail with a second amount).

BOTH = {"options": [opt("Kestrel Airways", 1800.0, 7), opt("Gannet Airways", 2400.0, 2)],
        "chosen": opt("Kestrel Airways", 1800.0, 7), "why": "cheapest"}
BOTH_FAST = {**BOTH, "chosen": opt("Gannet Airways", 2400.0, 2), "why": "fastest"}


def body_with(phrase):
    return f"Hi,\n\n{phrase} 3 pallets, 420 kg, 1.8 cbm, FRA to ORD, ready 2026-11-25.\n\nThanks,\nLaura"


@pytest.mark.parametrize("phrase, ask, canned, quoted, other", [
    ("Please quote the cheapest and the fastest option.", "cheapest", BOTH, "Kestrel Airways", "Gannet Airways"),
    ("Please quote the cheapest and the fastest option.", None, BOTH, "Kestrel Airways", "Gannet Airways"),
    ("We need it as fast as possible, but the price matters too.", "fastest", BOTH_FAST, "Gannet Airways",
     "Kestrel Airways"),
    ("Best price please, but it should be quick.", "cheapest", BOTH, "Kestrel Airways", "Gannet Airways"),
], ids=["both-ask-cheapest", "both-ask-unread", "fastest-price-matters", "best-price-but-quick"])
def test_cheapest_and_fastest_quotes_one_amount_and_names_the_other_in_words(phrase, ask, canned, quoted, other,
                                                                             backend_url, monkeypatch, tmp_path):
    api = Api(backend_url, canned)
    _, [quote] = run(monkeypatch, tmp_path, api, mail(body_with(phrase)), raw(ask=ask))
    chosen = api.quote()
    assert chosen["carrier"] == quoted and amounts(quote["body"]) == [f"{chosen['total']:,.2f}"]
    assert other in quote["body"] and not api.held()


def test_german_cheapest_and_fastest_names_the_other_option_in_german(backend_url, monkeypatch, tmp_path):
    body = ("Hallo,\n\nbitte die günstigste und die schnellste Option: 3 Paletten, 420 kg, 1,8 cbm, FRA nach ORD, "
            "bereit am 25.11.2026.\n\nViele Grüße\nAnna")
    api = Api(backend_url, BOTH)
    _, [quote] = run(monkeypatch, tmp_path, api, mail(body), raw(language="de"))
    assert amounts(quote["body"]) == ["1,800.00"] and "Gannet Airways" in quote["body"]
    assert "schneller" in quote["body"]


def test_a_single_ask_adds_no_other_option(backend_url, monkeypatch, tmp_path):
    _, [quote] = run(monkeypatch, tmp_path, Api(backend_url, BOTH), mail(body_with("Cheapest option please.")), raw())
    assert amounts(quote["body"]) == ["1,800.00"] and "Gannet" not in quote["body"]


@pytest.mark.parametrize("phrase", [
    "As fast as possible within a budget of EUR 2,000 please.",
    "Fastest option please, but no more than EUR 2,000.",
    "As fast as possible please, our budget is 2.000 EUR.",
    "Fastest possible, max. 2,000 EUR all-in.",
], ids=["budget-of-eur", "no-more-than", "amount-before-currency", "max-amount-eur"])
def test_fastest_within_a_budget_quotes_the_fastest_option_inside_it(phrase, backend_url, monkeypatch, tmp_path):
    api = Api(backend_url, BOTH_FAST)
    _, [quote] = run(monkeypatch, tmp_path, api, mail(body_with(phrase)), raw(ask="fastest"))
    assert api.quote()["carrier"] == "Kestrel Airways" and amounts(quote["body"]) == ["1,800.00"]


# ---- 3. a correction before our quote --------------------------------------------------------------------------------
# The customer corrects the RFQ in its thread while we collect bids: the quote must price the corrected request.

def correction_during(api, rfq_mail, text, carriers=AIRLINES):
    """A customer correction in the RFQ's thread, routed by the real dispatcher while the bids are outstanding."""
    def send(box, board):
        fix = {**mail(text, subject="Re: " + rfq_mail["subject"], thread_id=rfq_mail["thread_id"])}
        main.dispatch(fix, box, api, board, list(carriers))
        give_up = time.time() + 5
        while not amendments._pending.get(rfq_mail["thread_id"]) and time.time() < give_up:
            time.sleep(0.01)
    return send


def by_text(first, corrected, word="orre"):
    return lambda m: corrected if word in m["body"] else first


EXPENSIVE = {"Aurelia Air Cargo": [(0.3, bid(9000, 3, "AU-1"))], "Borealis Freight": [(0.3, bid(9100, 3, "BO-1"))]}


@pytest.mark.parametrize("text, corrected", [
    ("Sorry, correction: it's 4 pallets, not 3. Total weight 560 kg, 2.4 cbm.", raw(pieces=[piece(4, 560)], volume=2.4)),
    ("Korrektur: es sind 4 Paletten statt 3, insgesamt 560 kg, 2,4 cbm.", raw(pieces=[piece(4, 560)], volume=2.4)),
    ("Correction: the gross weight is 850 kg, not 420 kg.", raw(pieces=[piece(3, 850)])),
], ids=["en-pallets", "de-pallets", "en-weight"])
def test_a_correction_before_the_quote_is_priced(text, corrected, backend_url, monkeypatch, tmp_path):
    m = mail(body_with("Cheapest option please."))
    api = Api(backend_url)
    _, [quote] = run(monkeypatch, tmp_path, api, m, by_text(raw(), corrected), AIRLINES, EXPENSIVE,
                     correction_during(api, m, text))
    right = best(backend_url, as_rfq(corrected))["chosen"]
    assert abs(total_kg(api.priced[-1][0]) - total_kg(as_rfq(corrected))) < 0.01
    assert api.quote()["total"] == right["total"]


def test_a_destination_correction_never_uses_a_bid_for_the_old_lane(backend_url, monkeypatch, tmp_path):
    """The airlines bid for FRA-ORD; the customer then says JFK. Their bids are no price for FRA-JFK."""
    m = mail(body_with("Cheapest option please."))
    api = Api(backend_url)
    corrected = raw(destination="JFK")
    cheap = {"Aurelia Air Cargo": [(0.3, bid(300, 3, "AU-2"))], "Borealis Freight": [(0.3, bid(320, 3, "BO-2"))]}
    _, [quote] = run(monkeypatch, tmp_path, api, m, by_text(raw(), corrected), AIRLINES, cheap,
                     correction_during(api, m, "Correction: the destination is JFK, not ORD."))
    assert api.priced[-1][0]["destination"] == "JFK"
    assert api.quote()["source"] == "sheet" and api.quote()["total"] == best(backend_url, as_rfq(corrected))["chosen"]["total"]


def test_a_weight_correction_never_quotes_a_bid_for_the_old_weight(backend_url, monkeypatch, tmp_path):
    m = mail(body_with("Cheapest option please."))
    api = Api(backend_url)
    corrected = raw(pieces=[piece(6, 840)], volume=3.6)
    cheap = {"Aurelia Air Cargo": [(0.3, bid(950, 3, "AU-3"))], "Borealis Freight": [(0.3, bid(990, 3, "BO-3"))]}
    _, [quote] = run(monkeypatch, tmp_path, api, m, by_text(raw(), corrected), AIRLINES, cheap,
                     correction_during(api, m, "Correction: 6 pallets, 840 kg, 3.6 cbm (not 3 pallets)."))
    assert api.quote()["total"] == best(backend_url, as_rfq(corrected))["chosen"]["total"]


def test_a_correction_keeps_the_airline_the_customer_ruled_out(backend_url, monkeypatch, tmp_path):
    """R42 + a correction: the re-read must not bring the excluded airline back."""
    first = best(backend_url, as_rfq(raw(pieces=[piece(4, 560)], volume=2.4)))["chosen"]["carrier"]
    body = body_with(f"Cheapest option please. Please do not offer {first} for this shipment.")
    m = mail(body)
    api = Api(backend_url)
    ruled_out = [{"name": first, "email": "ruled-out@carrier.example", "kind": "airline", "serves": []}]
    corrected = raw(pieces=[piece(4, 560)], volume=2.4)
    _, [quote] = run(monkeypatch, tmp_path, api, m, by_text(raw(), corrected), AIRLINES + ruled_out, EXPENSIVE,
                     correction_during(api, m, "Correction: 4 pallets, 560 kg, 2.4 cbm."))
    assert abs(total_kg(api.priced[-1][0]) - 560) < 0.01
    assert api.quote()["carrier"] != first


def test_a_correction_in_the_same_poll_as_the_rfq_gives_one_quote_with_the_corrected_figures(
        backend_url, monkeypatch, tmp_path):
    """5U's customer corrects within a second: both mails come in one poll, before the session exists."""
    m = mail(body_with("Cheapest option please."))
    fix = mail("Sorry, correction: 4 pallets, 560 kg, 2.4 cbm.", subject="Re: Air freight request",
               thread_id=m["thread_id"])
    corrected = raw(pieces=[piece(4, 560)], volume=2.4)
    fake_reads(monkeypatch, by_text(raw(), corrected))
    api, box, board = Api(backend_url, slow_create=0.3), FixtureMailbox(tmp_path), BidBoard()
    threads = []

    def start(handler, *args):
        args = (*args, 3.0) if handler is rfq_agent.handle_rfq else args  # a 3 s bid round, not 90 s
        threads.append(t := threading.Thread(target=handler, args=args))
        t.start()
    monkeypatch.setattr(main, "_start", start)
    main.dispatch(m, box, api, board, AIRLINES)
    main.dispatch(fix, box, api, board, AIRLINES)
    give_up = time.time() + 5
    while len([s for s in box.sent if s["thread_id"].startswith("out-")]) < 2 and time.time() < give_up:
        time.sleep(0.01)
    deliver(box, board, AIRLINES, EXPENSIVE)
    for t in threads:
        t.join(timeout=30)
    quotes = [s for s in box.sent if s["thread_id"] == m["thread_id"]]
    assert len(quotes) == 1 and abs(total_kg(api.priced[-1][0]) - 560) < 0.01


@XF("amendments are read once, right after the carrier round: a correction that arrives while the gate holds the "
    "quote (up to GATE_AUTO_SEND_SECONDS) is parked and never read, the held quote goes out with the old figures")
def test_a_correction_while_the_gate_holds_the_quote_is_still_read(backend_url, monkeypatch, tmp_path):
    body = body_with("Cheapest option please, quote in USD.")  # the currency hold
    m = mail(body)
    api = Api(backend_url)
    corrected = raw(pieces=[piece(4, 560)], volume=2.4)
    monkeypatch.setattr(rfq_agent, "GATE_AUTO_SEND_SECONDS", 1.0)
    monkeypatch.setattr(rfq_agent, "_sleep", time.sleep)
    fake_reads(monkeypatch, by_text(raw(), corrected))
    box, board = FixtureMailbox(tmp_path), BidBoard()
    worker = threading.Thread(target=rfq_agent.handle_rfq, args=(m, box, api, board, [], 3.0))
    worker.start()
    give_up = time.time() + 5
    while not any(t.startswith("Quote held") for t in api.texts()) and time.time() < give_up:
        time.sleep(0.01)
    main.dispatch(mail("Correction: 4 pallets, 560 kg, 2.4 cbm.", thread_id=m["thread_id"]), box, api, board, [])
    worker.join(timeout=30)
    assert abs(total_kg(api.priced[-1][0]) - 560) < 0.01


# ---- 4. December ready dates and tariff mails -----------------------------------------------------------------------
# All start-kit sheets are valid 1-30 Nov 2026 (KIT_SUMMARY §7: "RFQs with a December ship date need the new monthly
# tariffs that airlines send by mail").

def test_a_december_ready_date_is_never_priced_from_a_november_sheet(backend_url, monkeypatch, tmp_path):
    """FRA-PVG: Helix's November sheet only. No December sheet, no portal, no bid: no price, a person answers."""
    assert best(backend_url, as_rfq(raw(destination="PVG")))["chosen"]["carrier"] == "Helix Air Freight"
    api = Api(backend_url)
    _, quotes = run(monkeypatch, tmp_path, api, mail(body_with("Cheapest please.")),
                    raw(destination="PVG", ready_date="2026-12-03"))
    assert quotes == [] and "needs_human" in api.kinds()
    assert not any(o["valid_until"] == "2026-11-30" for _, _, d in api.log if d and "options" in d for o in d["options"])


def december_txt(text_month="Valid from  01.12.2026\nValid to    31.12.2026", factor=2.0) -> bytes:
    """Yellowtail's November layout as a December tariff: its rates × factor."""
    text = (KIT / "yellowtail-air-freight-tariff-2026-11.txt").read_text()
    text = text.replace("Valid from  01.11.2026\nValid to    30.11.2026", text_month)
    return re.sub(r"EUR (\d+\.\d{2})(?=\s)", lambda m: f"EUR {float(m[1]) * factor:.2f}", text).encode()


def tariff_mail(filename, content: bytes, sender="yellowtail-air-freight@hackloop.mail"):
    return mail("Dear partner,\n\nplease find attached our tariff for December 2026.\n\nKind regards,\nYellowtail",
                subject="Yellowtail Air Freight tariff December 2026", sender=sender,
                attachments=[{"id": next(IDS), "filename": filename,
                              "content_base64": base64.b64encode(content).decode()}])


def dispatch_tariff(api, tmp_path, m, monkeypatch):
    monkeypatch.setattr(main, "_start", lambda handler, *args: handler(*args))  # run the ingestion here
    main.dispatch(m, FixtureMailbox(tmp_path), api, BidBoard(), load_carriers(KIT_LIST))


def test_a_december_tariff_mail_is_ingested_and_prices_december_rfqs(backend_url, monkeypatch, tmp_path):
    api = Api(backend_url)
    dispatch_tariff(api, tmp_path, tariff_mail("yellowtail-air-freight-tariff-2026-12.txt", december_txt()),
                    monkeypatch)
    december = raw(ready_date="2026-12-03")
    right = best(backend_url, as_rfq(december))["chosen"]
    assert right["carrier"] == "Yellowtail Air Freight" and right["valid_until"] == "2026-12-31"
    _, [quote] = run(monkeypatch, tmp_path, api, mail(body_with("Cheapest please.")), december)
    assert api.quote()["total"] == right["total"] and amounts(quote["body"]) == [f"{right['total']:,.2f}"]
    # November RFQs keep the November sheets (the December rates are × 2)
    november = best(backend_url, as_rfq(raw()))
    yellow = next(o for o in november["options"] if o["carrier"] == "Yellowtail Air Freight")
    assert yellow["valid_until"] == "2026-11-30" and yellow["total"] < right["total"]


XLSX_DECEMBER = r'''
import base64, datetime, io, json, sys
import openpyxl
name = json.loads(sys.stdin.read())
book = openpyxl.load_workbook("data/start-kit/" + name)
for sheet in book.worksheets:
    for row in sheet.iter_rows():
        for cell in row:
            v = cell.value
            if isinstance(v, (datetime.datetime, datetime.date)):
                cell.value = v.replace(month=12, day=31 if v.day == 30 else v.day)
            elif isinstance(v, str):
                cell.value = v.replace("2026-11-01", "2026-12-01").replace("2026-11-30", "2026-12-31") \
                              .replace("01.11.2026", "01.12.2026").replace("30.11.2026", "31.12.2026")
out = io.BytesIO(); book.save(out)
print(json.dumps(base64.b64encode(out.getvalue()).decode()))
'''


@pytest.mark.parametrize("name", ["kestrel-airways-tariff-2026-11.xlsx", "wayzata-air-cargo-tariff-2026-11.xlsx",
                                  "vega-skyfreight-tariff-2026-11.xlsx", "elbflug-air-freight-tariff-2026-11.xlsx"])
def test_a_december_xlsx_tariff_in_a_start_kit_layout_is_ingested(name, backend_url):
    content = in_backend(XLSX_DECEMBER, name)
    out = Backend(backend_url).ingest_tariff(name.replace("2026-11", "2026-12"), content, "airline@hackloop.mail")
    assert out.get("rows", 0) > 0 and out.get("valid_until") == "2026-12-31", out


@pytest.mark.parametrize("validity", [
    "Validity: 01.12.2026 - 31.12.2026",
    "Valid from December 1, 2026\nValid to December 31, 2026",
    "Gültig vom 01.12.2026 bis 31.12.2026",
    "",  # no validity line at all: the file name says 2026-12
], ids=["one-line-range", "month-first", "german", "file-name-only"])
def test_a_december_tariff_with_other_validity_wording_is_ingested(validity, backend_url):
    content = base64.b64encode(december_txt(validity)).decode()
    out = Backend(backend_url).ingest_tariff("yellowtail-air-freight-tariff-2026-12.txt", content,
                                             "yellowtail-air-freight@hackloop.mail")
    assert out.get("rows") == 15 and out.get("valid_until") == "2026-12-31", out


# ---- 5. units ------------------------------------------------------------------------------------------------------
# The model copies numbers and names their units; code converts. Real pricing on FRA-ORD (two sheets): the quote must
# equal the backend's price for the request read correctly.

def priced_like(backend_url, monkeypatch, tmp_path, body, reads, correct):
    api = Api(backend_url)
    _, quotes = run(monkeypatch, tmp_path, api, mail(body), reads)
    right = best(backend_url, as_rfq(correct))["chosen"]
    return api, quotes, right


LB_IN = "Hi,\n\n2 crates, 48 x 40 x 50 in, 1,100 lbs each, FRA to ORD, ready 2026-11-25.\n\nThanks,\nMike"
LB_IN_RAW = raw(pieces=[piece(2, 1100, False, 48, 40, 50)], volume=None, dim_unit="in", weight_unit="lb")
LIGHT_IN = "Hi,\n\n4 boxes, 48 x 40 x 60 in, 66 lbs each, FRA to ORD, ready 2026-11-25.\n\nThanks,\nMike"
LIGHT_IN_RAW = raw(pieces=[piece(4, 66, False, 48, 40, 60)], volume=None, dim_unit="in", weight_unit="lb")


@pytest.mark.parametrize("body, reads", [
    (LB_IN, LB_IN_RAW),
    ("Hallo,\n\n3 Kisten, gesamt 1.234,5 kg, 2,65 m³, FRA nach ORD, bereit 25.11.2026.\n\nGrüße\nJan",
     raw(pieces=[piece(3, 1234.5)], volume=2.65, language="de")),
    ("Hi,\n\none machine, 2 t, 3.2 cbm, FRA to ORD, ready 2026-11-25.\n\nThanks,\nMike",
     raw(pieces=[piece(1, 2)], volume=3.2, weight_unit="t")),
    ("Hi,\n\n3 pallets, 240 kg each, 1.8 cbm in total, FRA to ORD, ready 2026-11-25.\n\nThanks,\nMike",
     raw(pieces=[piece(3, 240, False)], volume=1.8)),
    ("Hi,\n\n2 crates of 1.8 cbm each, 150 kg each, FRA to ORD, ready 2026-11-25.\n\nThanks,\nMike",
     raw(pieces=[piece(2, 150, False, volume=1.8, volume_total=False)], volume=None)),
], ids=["lbs-inches", "german-decimals", "tonnes", "per-piece", "per-piece-volume"])
def test_units_read_right_are_priced_right(body, reads, backend_url, monkeypatch, tmp_path):
    api, [quote], right = priced_like(backend_url, monkeypatch, tmp_path, body, reads, reads)
    assert api.quote()["total"] == right["total"]


@pytest.mark.parametrize("reads, chargeable", [
    (raw(pieces=[piece(1, 300)], volume=4.0), 668.0),  # 4 cbm × 167
    (raw(pieces=[piece(2, 150, False, 120, 100, 150)], volume=None), 601.2),  # 2 × 1.8 cbm × 167
    (LB_IN_RAW, 997.9),  # 2 × 1,100 lb = 997.9 kg beats 3.15 cbm × 167 = 525.4 kg
], ids=["volume-given", "dims-given", "lbs-inches"])
def test_volume_weight_dominant_is_billed_on_cbm_times_167(reads, chargeable, backend_url, monkeypatch, tmp_path):
    api = Api(backend_url)
    run(monkeypatch, tmp_path, api, mail("Hi,\n\nsee figures. FRA to ORD."), reads)
    assert api.quote()["chargeable_weight_kg"] == pytest.approx(chargeable, abs=0.05)


# What a weaker read returns: the number is right, its unit or its scope is not. A rule on the mail text catches it.
@pytest.mark.parametrize("body, misread, correct", [
    ("Hi,\n\n2 crates, 1,100 lbs each, 3.1 cbm, FRA to ORD, ready 2026-11-25.\n\nThanks,\nMike",
     raw(pieces=[piece(2, 1100, False)], volume=3.1), raw(pieces=[piece(2, 1100, False)], volume=3.1, weight_unit="lb")),
    (LIGHT_IN, {**LIGHT_IN_RAW, "dim_unit": "cm"}, LIGHT_IN_RAW),
    ("Hi,\n\none machine, 2 t, 3.2 cbm, FRA to ORD, ready 2026-11-25.\n\nThanks,\nMike",
     raw(pieces=[piece(1, 2)], volume=3.2), raw(pieces=[piece(1, 2)], volume=3.2, weight_unit="t")),
    ("Hi,\n\n3 pallets, 240 kg each, 1.8 cbm in total, FRA to ORD, ready 2026-11-25.\n\nThanks,\nMike",
     raw(pieces=[piece(3, 240, True)], volume=1.8), raw(pieces=[piece(3, 240, False)], volume=1.8)),
    ("Hi,\n\n3 pallets, total weight 720 kg, 1.8 cbm, FRA to ORD, ready 2026-11-25.\n\nThanks,\nMike",
     raw(pieces=[piece(3, 720, False)], volume=1.8), raw(pieces=[piece(3, 720, True)], volume=1.8)),
    ("Hallo,\n\n3 Kisten, gesamt 1.234,5 kg, 2,65 m³, FRA nach ORD, bereit 25.11.2026.\n\nGrüße\nJan",
     raw(pieces=[piece(3, 1.2345)], volume=2.65, language="de"), raw(pieces=[piece(3, 1234.5)], volume=2.65, language="de")),
    ("Hallo,\n\n3 Kisten, gesamt 1.234,5 kg, 2,65 m³, FRA nach ORD, bereit 25.11.2026.\n\nGrüße\nJan",
     raw(pieces=[piece(3, 1234.5)], volume=265, language="de"), raw(pieces=[piece(3, 1234.5)], volume=2.65, language="de")),
], ids=["lbs-read-as-kg", "inches-read-as-cm", "tonnes-read-as-kg", "each-read-as-total", "total-read-as-each",
        "german-decimal-misread", "german-cbm-misread"])
def test_a_unit_or_scope_misread_is_caught_by_the_mail_text(body, misread, correct, backend_url, monkeypatch, tmp_path):
    api, quotes, right = priced_like(backend_url, monkeypatch, tmp_path, body, misread, correct)
    assert api.quote() and api.quote()["total"] == right["total"]


@pytest.mark.parametrize("body, reads", [
    ("Hi,\n\n2 crates, 1,100 lbs (499 kg) each, 3.1 cbm, FRA to ORD.\n\nThanks", raw(pieces=[piece(2, 499, False)], volume=3.1)),
    ("Hi,\n\n3 pallets à 120x80x100 cm, 240 kg, FRA to ORD.\n\nThanks", raw(pieces=[piece(3, 240, True, 120, 80, 100)], volume=None)),
    ("Hi,\n\n3 pallets, 240 kg each (720 kg in total), 1.8 cbm, FRA to ORD.\n\nThanks", raw(pieces=[piece(3, 720, True)], volume=1.8)),
    ("Hi,\n\n2 crates 120 x 80 x 100 cm, max. stack height 60 in, 400 kg, FRA to ORD.\n\nThanks",
     raw(pieces=[piece(2, 400, True, 120, 80, 100)], volume=None)),
], ids=["mixed-units", "a-is-ambiguous", "each-and-total", "inches-elsewhere"])
def test_a_reading_the_mail_supports_is_left_alone(body, reads, backend_url, monkeypatch, tmp_path):
    api, _, right = priced_like(backend_url, monkeypatch, tmp_path, body, reads, reads)
    assert api.quote()["total"] == right["total"]


def test_tonnes_read_as_kg_are_read_right_before_the_density_net(monkeypatch):
    """test_rfq_agent's density case: the "t" next to 2.4 sets the unit, no hand-over (that test pins the net off)."""
    tonnes_as_kg = raw(pieces=[piece(9, 2.4, True)], volume=14)
    monkeypatch.setattr(extract_mod, "extract", lambda m, model="gpt-6-luna": (tonnes_as_kg, 0.0001))
    read = extract_mod.read_request(mail("9 pieces, gross weight 2.4 t, 14 cbm, FRA to ORD, ready 2026-11-25"))
    assert round(total_kg(read["rfq"])) == 2400 and not read["missing"] and not read["escalated"]


# ---- 6. Incoterms and door wording -----------------------------------------------------------------------------------

PICKUP_CANNED = {"options": [{**opt("SkyAir", 1500.0, 2), "pickup": {"carrier": "Isarwelle", "total": 120.0}}],
                 "chosen": {**opt("SkyAir", 1500.0, 2), "pickup": {"carrier": "Isarwelle", "total": 120.0}}}


@pytest.mark.parametrize("body, read_origin, origin", [
    ("Hello,\n\nplease quote your cheapest all-in rate to JFK. Terms are EXW our plant, Industriestr. 12, "
     "85748 Garching. 2 crates, 440 kg total, 1.9 cbm, ready 2026-11-24.\n\nMax Huber", "MUC", "MUC"),
    ("Hello,\n\nIncoterm FCA our warehouse, Am Hafen 3, 28197 Bremen. Cheapest air freight to JFK please: 2 crates, "
     "440 kg, 1.9 cbm, ready 24.11.2026.\n\nRegards,\nMax Huber", None, "HAM"),
    ("Hallo,\n\nLieferbedingung ab Werk (EXW) Ingolstadt. Bitte günstigste Luftfracht nach JFK: 2 Kisten, 440 kg, "
     "1,9 cbm, bereit am 24.11.2026.\n\nViele Grüße\nMax Huber", None, "MUC"),
], ids=["exw-postcode", "fca-warehouse-postcode", "exw-town"])
def test_exw_or_fca_at_a_german_site_is_priced_door_to_port(body, read_origin, origin, backend_url, monkeypatch,
                                                            tmp_path):
    api = Api(backend_url, PICKUP_CANNED)
    run(monkeypatch, tmp_path, api, mail(body),
        raw(origin=read_origin, destination="JFK", pieces=[piece(2, 440)], volume=1.9))
    assert api.priced, api.texts()
    priced = api.priced[0][0]
    assert priced["pickup"] and priced["origin"] == origin


@pytest.mark.parametrize("body", [
    "Hello,\n\nFCA Frankfurt Airport, cheapest to JFK: 2 crates, 440 kg, 1.9 cbm.\n\nRegards,\nMax Huber\n"
    "ACME GmbH, Hauptstr. 1, 60311 Frankfurt",
    "Hello,\n\nwe deliver the goods to FRA airport ourselves. Cheapest to JFK: 2 crates, 440 kg, 1.9 cbm.\n\n"
    "Regards,\nMax Huber",
    "Hello,\n\nincoterms CPT JFK. Cheapest from FRA: 2 crates, 440 kg, 1.9 cbm.\n\nRegards,\nMax Huber",
    "Hello,\n\nterms FCA Frankfurt. Cheapest to JFK please: 2 crates, 440 kg, 1.9 cbm.\n\nRegards,\nMax Huber",
], ids=["fca-airport-signature-postcode", "delivered-to-the-airport", "cpt", "fca-town-only"])
def test_airport_terms_stay_airport_to_airport(body, backend_url, monkeypatch, tmp_path):
    api = Api(backend_url, CANNED)
    _, [quote] = run(monkeypatch, tmp_path, api, mail(body),
                     raw(destination="JFK", pieces=[piece(2, 440)], volume=1.9))
    assert api.priced[0][0]["pickup"] is None
    assert "door" not in quote["body"].lower() and "customs" not in quote["body"].lower()


@pytest.mark.parametrize("body, language, words", [
    ("Hello,\n\nplease quote DDP Chicago, delivered to our customer's warehouse: 3 pallets, 420 kg, 1.8 cbm "
     "from FRA, ready 2026-11-25.\n\nRegards,\nMax", "en", ("not included", "customs")),
    ("Hello,\n\nDAP Chicago please, 3 pallets, 420 kg, 1.8 cbm from FRA, ready 2026-11-25.\n\nRegards,\nMax", "en",
     ("not included",)),
    ("Hello,\n\nwe need a door-to-door quote FRA to Chicago: 3 pallets, 420 kg, 1.8 cbm, ready 2026-11-25.\n\n"
     "Regards,\nMax", "en", ("not included",)),
    ("Hello,\n\nplease include delivery to the consignee's address in Chicago: 3 pallets, 420 kg, 1.8 cbm from FRA, "
     "ready 2026-11-25.\n\nRegards,\nMax", "en", ("not included",)),
    ("Hallo,\n\nbitte DDP Chicago inklusive Zustellung beim Empfänger anbieten: 3 Paletten, 420 kg, 1,8 cbm ab FRA, "
     "bereit 25.11.2026.\n\nViele Grüße\nMax", "de", ("nicht enthalten",)),
], ids=["ddp", "dap", "door-to-door", "delivery-to-consignee", "german-ddp"])
def test_delivery_at_destination_is_never_quoted_airport_to_airport_silently(body, language, words, backend_url,
                                                                             monkeypatch, tmp_path):
    api = Api(backend_url, CANNED)
    _, [quote] = run(monkeypatch, tmp_path, api, mail(body), raw(language=language))
    assert amounts(quote["body"]) == ["2,400.00"]
    assert all(w in quote["body"] for w in words), quote["body"]


# ---- 7. places -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field, value, code", [
    ("origin", "Munich", "MUC"),
    ("origin", "Frankfurt am Main", "FRA"),
    ("origin", "Munich Airport (MUC)", "MUC"),
    ("origin", "Flughafen Düsseldorf", "DUS"),
    ("destination", "New York", "JFK"),
    ("destination", "Chicago O'Hare", "ORD"),
], ids=["city", "city-long-name", "airport-name-and-code", "german-airport-name", "two-airport-city", "airport-name"])
def test_a_city_or_airport_name_becomes_the_code_we_price(field, value, code):
    rfq, missing = extract_mod.to_rfq(raw(**{field: value}))
    assert rfq[field] == code and not missing


@pytest.mark.parametrize("destination, priced", [
    ("NYC", "JFK"), ("EWR", "JFK"), ("Newark", "JFK"), ("Tokyo Haneda", "NRT"), ("HND", "NRT"),
], ids=["nyc", "ewr", "newark-name", "haneda-name", "hnd"])
def test_a_city_with_two_airports_is_priced_at_the_one_our_lanes_fly(destination, priced, backend_url, monkeypatch,
                                                                     tmp_path):
    api = Api(backend_url)
    _, [quote] = run(monkeypatch, tmp_path, api, mail(f"Hi,\n\n3 pallets, 420 kg, 1.8 cbm, FRA to {destination}."),
                     raw(destination=destination))
    assert api.quote()["total"] == best(backend_url, as_rfq(raw(destination=priced)))["chosen"]["total"]


@pytest.mark.parametrize("origin", ["VIE", "Vienna", "ZRH"])
def test_an_origin_outside_germany_is_never_quoted_from_a_german_airport(origin, backend_url, monkeypatch, tmp_path):
    api = Api(backend_url)
    _, quotes = run(monkeypatch, tmp_path, api, mail(f"Hi,\n\n3 pallets, 420 kg, 1.8 cbm from {origin} to ORD."),
                    raw(origin=origin))
    assert quotes == [] and "needs_human" in api.kinds()
    assert all(p[0]["origin"] == origin for p in api.priced)


@pytest.mark.parametrize("town, zone, airport", [("Ingolstadt", "85", "MUC"), ("Augsburg", "86", "MUC"),
                                                 ("Bremen", "28", "HAM"), ("Bonn", "53", "CGN")])
def test_an_origin_town_without_an_airport_is_door_to_port_from_its_zone(town, zone, airport):
    rfq, missing = extract_mod.to_rfq(raw(origin=town))
    assert rfq["origin"] == airport and rfq["pickup"]["zone"] == zone and not missing
