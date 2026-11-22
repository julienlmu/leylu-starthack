"""PORTAL_RETRY (R93 / session 95, 0/13 teams too_low): the portal answered 503, every team quoted the sheet price and
5U's reference was the portal's. The portal is asked again with growing pauses until PORTAL_RETRY_LAST_SECONDS; the
sheet price goes out only as the last resort. Fakes only: no 5U, no gateway, no LLM."""

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
