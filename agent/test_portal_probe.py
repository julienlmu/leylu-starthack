"""PORTAL_PROBE (R95 follow-up): the portal is priced once right after extraction; down → the web-form push at T+0,
with every portal airline on the lane, and the retry after the cut-off doesn't push it twice. Fakes only."""

import rfq_agent

DOWN = {"options": [], "chosen": None,
        "why": "No price; portal: rates GN: 503 {\"detail\":\"The rate API is unavailable.\"} (lane airlines: GN, MD)"}
UP = {"options": [], "chosen": None, "why": "cheapest: Gannet Airways (portal)"}
RFQ = {"origin": "FRA", "destination": "LAX", "volume_m3": 1.1,
       "pieces": [{"count": 1, "length_cm": None, "width_cm": None, "height_cm": None, "weight_kg": 300}]}


class Api:
    def __init__(self, result):
        self.result, self.events = result, []

    def price(self, rfq, bids):
        return self.result

    def event(self, session_id, kind, text, data=None):
        self.events.append((kind, text))


def test_a_portal_down_at_t0_pushes_the_form_with_every_lane_airline():
    api = Api(DOWN)
    rfq_agent._PROBED.discard(41)
    rfq_agent.portal_probe(41, RFQ, api).join(5)
    (kind, text), = api.events
    assert kind == "needs_human" and "Origin FRA, Destination LAX, Weight 300 kg" in text
    assert "airlines: GN, MD" in text and "portal_rate.py 41" in text and 41 in rfq_agent._PROBED
    rfq_agent.portal_probe(41, RFQ, api).join(5)
    assert len(api.events) == 1  # once per session


def test_a_working_portal_or_the_switch_off_pushes_nothing(monkeypatch):
    api = Api(UP)
    rfq_agent.portal_probe(42, RFQ, api).join(5)
    assert api.events == []
    monkeypatch.setattr(rfq_agent, "PORTAL_PROBE", False)
    assert rfq_agent.portal_probe(43, RFQ, Api(DOWN)) is None


def test_a_failing_backend_never_breaks_the_probe():
    class Broken(Api):
        def price(self, rfq, bids):
            raise RuntimeError("backend down")
    api = Broken(DOWN)
    rfq_agent.portal_probe(44, RFQ, api).join(5)
    assert api.events == []


def test_the_push_starts_with_a_prefilled_portal_link():
    text = rfq_agent._portal_text(41, RFQ, DOWN["why"])
    assert text.startswith("Portal API down. Open https://start-hack.5u.ai/portal/ui#s=41&o=FRA&d=LAX&w=300&v=1.1&a=GN,MD ")
    assert "key" not in rfq_agent.portal_link(41, RFQ, DOWN["why"]).lower()
    assert len(("#41: " + text)[:300].split(" , ")[0]) < 300  # the link survives ntfy's 300 characters


def test_a_rate_typed_during_the_bid_round_is_kept_and_quoted_without_the_desk(tmp_path, monkeypatch):
    """The T+0 push lets a person type a portal rate before the cut-off: the agent's own bid update must keep it, and it
    is quoted at once (no rate desk round, no retry)."""
    import portal_rate
    import test_next_traps_15b as t15

    typed = portal_rate.stored_rate("Gannet Airways", "612.40", "2", "R-UI1")
    up = {"options": [t15._option("Gannet Airways", 612.40)], "chosen": t15._option("Gannet Airways", 612.40),
          "why": "fastest: Gannet Airways (bid); portal: rates GN: 503 unavailable"}
    real_session = t15.Api.session
    monkeypatch.setattr(t15.Api, "session", lambda self, sid: {**real_session(self, sid), "bids": [typed]})
    box, api, desk = t15._run(tmp_path, monkeypatch, [up], None)
    assert "612.40" in box.sent[-1]["body"] and desk == []
    assert typed in api.prices[-1]
    assert all(typed in u["bids"] for u in api.updates if "bids" in u)


def test_a_rate_typed_while_the_desk_also_answered_is_still_priced(tmp_path, monkeypatch):
    """The rate desk answered AND a person typed a portal rate during its wait: the quote is priced with the typed rate
    too (it used to be stored in the CRM but left out of the price the quote came from)."""
    import portal_rate
    import test_next_traps_15b as t15

    typed = portal_rate.stored_rate("Gannet Airways", "612.40", "2", "R-UI1")
    down = {"options": [t15._option("Wayzata", 980.0, "sheet")], "chosen": t15._option("Wayzata", 980.0, "sheet"),
            "why": "cheapest: Wayzata (sheet); portal: rates GN: 503 unavailable"}
    with_typed = {**down, "chosen": t15._option("Gannet Airways", 612.40),
                  "options": [t15._option("Gannet Airways", 612.40)]}
    monkeypatch.setattr(t15.Api, "price", lambda self, rfq, bids=None, fallback=False: (
        self.prices.append(list(bids or [])) or (with_typed if typed in (bids or []) else down)))
    real_session = t15.Api.session
    monkeypatch.setattr(t15.Api, "session", lambda self, sid: {**real_session(self, sid),
                                                              "bids": [typed] if self.prices else []})
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: None)
    monkeypatch.setattr(rfq_agent, "PORTAL_MANUAL_GRACE", 0)
    monkeypatch.setattr(rfq_agent, "PORTAL_PROBE", False)  # its price call would show the typed rate too early

    class KeepRetry:  # _run turns the retry off: keep it on
        def setattr(self, obj, name, value):
            monkeypatch.setattr(obj, name, 60 if (obj is rfq_agent and name == "PORTAL_RETRY_LAST_SECONDS") else value)
    box, api, desk = t15._run(tmp_path, KeepRetry(), [down], "Rate FRA-LAX: Wayzata\nTotal: 980.00 EUR\nTransit: 3 days")
    assert len(desk) == 1 and "612.40" in box.sent[-1]["body"]
    assert typed in api.prices[-1]
