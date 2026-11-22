"""IMPORT_DECLINE (session 164): NRT → HAM airport-to-airport is an import into Germany. We only sell air exports
from German airports: an honest decline at once, no price, no carrier asked. A normal export is never caught."""
import pytest

import extract as extract_mod
import import_trap
import rfq_agent
from bids import BidBoard
from inbox import FixtureMailbox
from test_next_traps_15b import CARRIERS, MAIL, RAW, Api

S164 = {"subject": "RFQ Narita - Hamburg", "body": "Hello, please quote airport to airport NRT to HAM: 2 pallets, "
                                                  "640 kg, 3.1 cbm, ready Monday. Cheapest option please."}


def test_session_164_nrt_to_ham_is_caught():
    assert "NRT" in import_trap.caught({"origin": "NRT", "destination": "HAM"}, S164)


@pytest.mark.parametrize("origin", ["PVG", "JFK", "ICN", "DXB", "ZRH", "VIE"])
def test_an_origin_abroad_is_caught(origin):
    assert import_trap.caught({"origin": origin, "destination": "FRA"}, {"subject": "RFQ", "body": "300 kg"})


@pytest.mark.parametrize("body", [
    "We are importing 3 crates from Shenzhen, please quote the air freight to Frankfurt.",
    "This is an import shipment: 500 kg from Chicago, we're the consignee in Munich.",
    "Please quote: import from Japan, 2 pallets, arriving at HAM.",
    "We are the receiver. Our supplier hands over at Shanghai Pudong airport, 400 kg.",
    "Inbound shipment from Mumbai, 250 kg, to our Stuttgart plant.",
    "Wir sind der Empfänger, die Ware kommt aus Taiwan, 300 kg nach Frankfurt.",
    "Bitte Angebot für eine Importsendung aus Korea, 2 Paletten.",
])
def test_the_mail_says_import(body):
    assert import_trap.caught({"origin": "FRA", "destination": "LAX"}, {"subject": "RFQ", "body": body})


@pytest.mark.parametrize("origin, body", [
    ("FRA", "1 crate 120x80x100 cm, 300 kg, FRA to LAX, ready 25 Nov. Best price please."),
    ("MUC", "Export to Bangkok, 1,885 kg. Import duties at destination are paid by the consignee."),
    ("HAM", "DAP Chicago, the importer of record handles customs clearance. 400 kg, important: fragile."),
    ("DUS", "Please quote 2 pallets to Singapore. The import licence is already with the receiver."),
    ("STR", "Exportsendung nach Dubai, 500 kg. Einfuhrabgaben trägt der Empfänger."),
    (None, "Pickup at 60413 Frankfurt am Main, 300 kg to Tel Aviv."),
    ("CGN", "Our supplier hands over at our Cologne warehouse. 200 kg to New York."),
])
def test_a_normal_export_is_never_caught(origin, body):
    assert import_trap.caught({"origin": origin, "destination": "LAX"}, {"subject": "RFQ", "body": body}) is None


def test_a_pickup_near_a_german_zone_is_no_import():
    # FOREIGN_PICKUP: "6020 Innsbruck, Austria" flies from MUC even if the reading put INN as the origin
    rfq = {"origin": "INN", "destination": "JFK", "pickup": {"address": "6020 Innsbruck, Austria", "zone": None}}
    assert import_trap.caught(rfq, {"subject": "RFQ", "body": "300 kg, pickup in Innsbruck"}) is None


def test_off(monkeypatch):
    monkeypatch.setattr(import_trap, "ON", False)
    assert import_trap.caught({"origin": "NRT", "destination": "HAM"}, S164) is None


def test_session_164_gets_the_decline_no_price_and_no_carrier_mail(tmp_path, monkeypatch):
    raw = {**RAW, "origin": "NRT", "destination": "HAM", "commodity": "pallets"}
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    box, api = FixtureMailbox(tmp_path), Api([{"options": [], "chosen": None, "why": ""}])
    rfq_agent.handle_rfq({**MAIL, **S164}, box, api, BidBoard(), CARRIERS, 0.2)
    [decline] = box.sent
    assert decline["thread_id"] == "t1" and "exports from German airports" in decline["body"]
    assert "EUR" not in decline["body"] and api.prices == []
    assert api.updates[-1]["stage"] == "done" and api.updates[-1]["needs_human"] is False
    assert not any(kind == "needs_human" for kind, _ in api.events)


def test_the_normal_fixture_rfq_is_not_caught():
    assert import_trap.caught({"origin": RAW["origin"], "destination": RAW["destination"], "pickup": None}, MAIL) is None


# ---- LANE_DECLINE (R159): every carrier refuses the lane and nothing priced it -------------------------------------

@pytest.mark.parametrize("body, refused", [
    ("We do not serve this lane/zone: NRT-HAM", True),
    ("Sorry, we don't fly this route.", True),
    ("Unfortunately we cannot serve this destination.", True),
    ("We do not serve this lane direct, but via AMS: total EUR 2,450, 3 days", False),
    ("Total: 2108.20 EUR\nTransit: 1 day", False),
    ("We have no capacity this week.", False),  # no lane word: not a lane refusal
])
def test_a_lane_refusal(body, refused):
    from bids import refuses_lane
    assert refuses_lane(body) is refused


def _round_trip(tmp_path, monkeypatch, answers):
    from test_traps2_bids import DeliveringBox
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    board = BidBoard()
    box = DeliveringBox(tmp_path, board, answers)
    api = Api([{"options": [], "chosen": None, "why": "No price for FRA-LAX"}])
    rfq_agent.handle_rfq(MAIL, box, api, board, CARRIERS, 5)
    return box, api


def test_every_carrier_refusing_the_lane_gets_the_decline_at_once(tmp_path, monkeypatch):
    import time
    start = time.time()
    box, api = _round_trip(tmp_path, monkeypatch, {c["email"]: ["We do not serve this lane/zone: FRA-LAX"]
                                                   for c in CARRIERS})
    decline = [m for m in box.sent if m.get("thread_id") == "t1"]
    assert len(decline) == 1 and "none of our airline partners serves this route" in decline[0]["body"]
    assert "EUR" not in decline[0]["body"] and api.updates[-1]["stage"] == "done"
    assert not any(kind == "needs_human" for kind, _ in api.events)
    assert time.time() - start < 5  # the round ends when the last refusal is in, not at the cut-off


def _carrier_round(tmp_path, answers):
    from test_rfq_agent import FakeApi
    from test_traps2_bids import RFQ, DeliveringBox
    board, rfq = BidBoard(), {**RFQ}
    box = DeliveringBox(tmp_path, board, answers)
    bids, _ = rfq_agent._carrier_round(1, {**MAIL, "received_at": None}, rfq, list(CARRIERS), box, FakeApi({}), board, 2)
    return bids, rfq


def test_one_real_bid_is_no_lane_refusal(tmp_path):
    bids, rfq = _carrier_round(tmp_path, {CARRIERS[0]["email"]: ["We do not serve this lane/zone: FRA-LAX"],
                                          CARRIERS[1]["email"]: ["Total: 1500.00 EUR\nTransit: 2 days\nRate ID: R-1"]})
    assert bids and "lane_refused" not in rfq


def test_every_refusal_is_noted_on_the_request(tmp_path):
    _, rfq = _carrier_round(tmp_path, {c["email"]: ["We do not serve this lane"] for c in CARRIERS})
    assert rfq["lane_refused"] == 2


def test_lane_decline_off(tmp_path, monkeypatch):
    monkeypatch.setattr(import_trap, "LANE", False)
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0)  # off: a person + the fallback at once, as before
    box, api = _round_trip(tmp_path, monkeypatch, {c["email"]: ["We do not serve this lane/zone: FRA-LAX"]
                                                   for c in CARRIERS})
    assert not any("refused the lane" in text for _, text in api.events)
    assert not any("none of our airline partners" in (m.get("body") or "") for m in box.sent)


@pytest.mark.parametrize("lang, start", [("de", "Guten Tag"), ("tr", "Merhaba"), ("fr", "Bonjour"), ("xx", "Hello")])
def test_the_decline_speaks_the_mail_language(lang, start):
    text = import_trap.decline_text(lang)
    assert text.startswith(start) and not any(c.isdigit() for c in text.split("\n\n")[1])
