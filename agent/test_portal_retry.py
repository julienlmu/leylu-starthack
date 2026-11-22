"""PORTAL_RETRY (R93 / session 95, 0/13 teams too_low): the portal answered 503, every team quoted the sheet price and
5U's reference was the portal's. The portal is asked again with growing pauses until PORTAL_RETRY_LAST_SECONDS; the
sheet price goes out only as the last resort. Fakes only: no 5U, no gateway, no LLM."""

import time
from datetime import datetime, timezone

import portal_rate
import rfq_agent
from test_next_traps_15b import _option, _run

SHEET = {"options": [_option("Wayzata", 488.30, "sheet")], "chosen": _option("Wayzata", 488.30, "sheet"),
         "why": "cheapest: Wayzata (sheet); portal: rates GN: 503 unavailable"}
PORTAL = {"options": [_option("Gannet Airways", 612.40, "portal"), _option("Wayzata", 488.30, "sheet")],
          "chosen": _option("Gannet Airways", 612.40, "portal"), "why": "fastest: Gannet Airways (portal)"}


def test_the_portal_answering_on_a_retry_is_quoted_not_the_sheet(tmp_path, monkeypatch):
    waits = []
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: waits.append(s))
    box, api, desk = _run_retry(tmp_path, monkeypatch, [SHEET, SHEET, SHEET, PORTAL])
    assert len(desk) == 1  # the rate desk was asked first (silent here)
    body = box.sent[-1]["body"]
    assert box.sent[-1]["thread_id"] == "t1" and "612.40" in body and "488.30" not in body
    assert waits[:2] == [10.0, 15.0] and len(api.prices) == 4
    assert any("Portal answered on retry" in text for _, text in api.events)


def test_a_portal_that_stays_down_quotes_the_sheet_price_at_the_deadline(tmp_path, monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    real_time = rfq_agent.time.time
    start = real_time()
    monkeypatch.setattr(rfq_agent.time, "time", lambda: start + clock["t"] + (real_time() - start))
    box, api, desk = _run_retry(tmp_path, monkeypatch, [SHEET], last=60)
    assert "488.30" in box.sent[-1]["body"] and 2 <= len(api.prices) <= 8
    assert any("Portal still unavailable" in text for _, text in api.events)


def test_portal_retry_off_quotes_the_sheet_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq_agent, "PORTAL_RETRY", False)
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: (_ for _ in ()).throw(AssertionError("no retry wait")))
    box, api, desk = _run_retry(tmp_path, monkeypatch, [SHEET, PORTAL], last=60)
    assert "488.30" in box.sent[-1]["body"]


def _run_retry(tmp_path, monkeypatch, results, last=60):
    """test_next_traps_15b._run (silent rate desk), with the portal retry on until `last` s after the RFQ."""
    class KeepRetry:  # _run turns the retry off for the rate desk tests: keep it on here
        def setattr(self, obj, name, value):
            monkeypatch.setattr(obj, name, last if (obj is rfq_agent and name == "PORTAL_RETRY_LAST_SECONDS") else value)
    return _run(tmp_path, KeepRetry(), results, None)


class _DownApi:
    """The portal stays down; from the 2nd look a person has typed a portal rate in (portal_rate.py)."""

    def __init__(self):
        self.looks, self.priced, self.events, self.updates = 0, [], [], []

    def session(self, session_id):
        self.looks += 1
        typed = portal_rate.stored_rate("Gannet Airways", "612.40", "2", "R-UI1")
        return {"bids": [typed] if self.looks >= 2 else []}

    def price(self, rfq, bids=None, fallback=False):
        self.priced.append(list(bids or []))
        if any(b.get("manual_portal") for b in bids or []):
            return {**SHEET, "chosen": _option("Gannet Airways", 612.40), "options": [_option("Gannet Airways", 612.40)]}
        return SHEET

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append((kind, text))

    def update(self, session_id, **fields):
        self.updates.append(fields)


RFQ = {"origin": "FRA", "destination": "LAX", "volume_m3": 1.1, "ask": "fastest",
       "pieces": [{"count": 2, "weight_kg": 150, "length_cm": None, "width_cm": None, "height_cm": None}]}


def test_a_rate_a_person_enters_from_the_portal_form_is_quoted(monkeypatch):
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: None)
    monkeypatch.setattr(rfq_agent, "PORTAL_MANUAL_GRACE", 0)
    api, bids = _DownApi(), []
    result = rfq_agent._portal_retry(7, {"received_at": None}, RFQ, bids, SHEET, api)
    assert result["chosen"]["total"] == 612.40 and bids[0]["manual_portal"]
    asked = next(text for kind, text in api.events if kind == "needs_human")
    assert "Origin FRA, Destination LAX, Weight 300 kg, Volume 1.1 cbm" in asked and "airlines: GN" in asked
    assert "portal_rate.py 7 <airline>" in asked
    assert api.updates[0] == {"needs_human": True} and api.updates[-1] == {"needs_human": False}


def test_the_form_line_and_the_stored_rate():
    assert rfq_agent.portal_form(RFQ) == ("Origin FRA, Destination LAX, Weight 300 kg, Volume 1.1 cbm (chargeable "
                                          "300 kg), airlines: every portal airline on the lane")
    assert portal_rate.stored_rate("GN", "1,234.50", "3") == {
        "source": "carrier_bid", "leg": "air", "carrier": "GN", "currency": "EUR", "total": 1234.5,
        "transit_days": 3.0, "rate_id": None, "manual_portal": True}


def _run_combined(tmp_path, monkeypatch, results, **times):
    """The whole RFQ with #239's long rate desk wait and the portal retry together, on a short clock (seconds)."""
    import extract as extract_mod
    from bids import BidBoard
    from inbox import FixtureMailbox
    from test_next_traps_15b import CARRIERS, MAIL, RAW, Api
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    monkeypatch.setattr(rfq_agent, "_portal_turn", [0.0, None])
    for name, value in {"RATEDESK_WAIT_SECONDS": 0.5, "RATEDESK_MIN_WAIT": 0.2, "PORTAL_RETRY_FIRST_WAIT": 0.3,
                        "PORTAL_MANUAL_GRACE": 0.5, **times}.items():
        monkeypatch.setattr(rfq_agent, name, value)
    mail = {**MAIL, "received_at": datetime.now(timezone.utc).isoformat()}
    box, api, board = FixtureMailbox(tmp_path), Api(results), BidBoard()
    rfq_agent.handle_rfq(mail, box, api, board, CARRIERS, 0.3)
    return box, api, rfq_agent.sent_at(mail)


def test_the_portal_back_during_the_rate_desk_wait_ends_the_wait_and_its_price_wins(tmp_path, monkeypatch):
    box, api, t0 = _run_combined(tmp_path, monkeypatch, [SHEET, SHEET, PORTAL], RATEDESK_UNTIL=6,
                                 PORTAL_POLL_SECONDS=0.4, PORTAL_RETRY_LAST_SECONDS=8, RATEDESK_LAST_SECONDS=9)
    assert any(m["to"] == "ratedesk@hackloop.mail" for m in box.sent)  # the desk was asked first
    assert "612.40" in box.sent[-1]["body"] and "488.30" not in box.sent[-1]["body"]
    assert any("Portal answered while we waited" in text for _, text in api.events)
    assert time.time() - t0 < 4  # quoted once the portal answered, not at the end of the 6 s desk wait


def test_a_portal_down_for_good_is_quoted_from_the_sheet_never_past_the_last_second(tmp_path, monkeypatch):
    box, api, t0 = _run_combined(tmp_path, monkeypatch, [SHEET], RATEDESK_UNTIL=2, PORTAL_POLL_SECONDS=0.4,
                                 PORTAL_RETRY_LAST_SECONDS=600, RATEDESK_LAST_SECONDS=3.5)
    assert "488.30" in box.sent[-1]["body"] and box.sent[-1]["thread_id"] == "t1"
    assert time.time() - t0 < 4.5  # PORTAL_RETRY_LAST_SECONDS can't push it past RATEDESK_LAST_SECONDS (T+4:30 live)
    assert len(api.prices) <= 12  # paced polls and retries, not a busy loop
    assert any("Portal still unavailable" in text for _, text in api.events)


def test_another_sessions_retry_goes_first(monkeypatch):
    monkeypatch.setattr(rfq_agent, "_portal_turn", [0.0, None])
    assert rfq_agent._portal_pace(1) == 0.0 and rfq_agent._portal_pace(1) == 0.0  # its own pace is its backoff
    assert rfq_agent.PORTAL_RETRY_GAP - 1 < rfq_agent._portal_pace(2) <= rfq_agent.PORTAL_RETRY_GAP
