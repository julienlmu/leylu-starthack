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
