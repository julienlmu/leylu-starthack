"""PORTAL_FORM: the rate API answers 503 (R93-R95) while the portal's web form still prices. The form is filled by each
field's kind and label (names and order change on every load), never a sum solved, never a field guessed."""
import asyncio
import json
import random
import re

import httpx
import pytest

import portal_form
from portal import Portal
from pricing import Pricer
from test_pricing import TARIFFS, rfq
from tariffs import Zones

FORM = "https://start-hack.5u.ai/portal/ui"
LABELS = {"origin": "Origin airport", "destination": "Destination airport", "airline": "Airline", "weight": "Weight (kg)",
          "volume": "Volume (cbm)", "key": "Team API key"}
KINDS = {"origin": "airport", "destination": "airport", "airline": "airline", "weight": "number", "volume": "number",
         "key": "password"}
PRICES = {"GN": 812.40, "MD": 765.10, "AU": 901.00}
NAMES = {"GN": "Gannet Airways", "MD": "Meridian Freightways", "AU": "Aurelia Air Cargo"}


class FakeForm:
    """The portal page's two POSTs, as in portal_ui.html: shuffled names and order, a consent value, an optional sum."""

    def __init__(self, labels=None, kinds=None, sum_=False, api_status=503, delay=0.0, result=None, extra=None):
        self.labels, self.kinds = labels or LABELS, kinds or KINDS
        self.sum, self.api_status, self.delay, self.result, self.extra = sum_, api_status, delay, result, extra or []
        self.loads, self.submits, self.api_calls, self.pages = {}, [], 0, 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "portal.test":  # the rate API
            self.api_calls += 1
            if request.url.path == "/v1/portal/ports":
                return httpx.Response(200, json={"lanes": [{"origin": "FRA", "destination": "LAX", "airlines": [
                    {"code": c, "name": n} for c, n in NAMES.items()]}]})
            if request.url.path == "/v1/portal/brackets":
                return httpx.Response(200, json={"breaks_kg": [0, 45, 100, 300, 500, 1000]})
            return httpx.Response(self.api_status, json={"detail": "The rate API is unavailable.", "retry_after": None})
        assert str(request.url).startswith(FORM)
        if request.method == "GET":
            self.pages += 1
            return httpx.Response(200, text="<html>portal</html>", headers={"set-cookie": "sid=abc; Path=/"})
        if self.delay:
            await asyncio.sleep(self.delay)
        if request.headers.get("X-Portal-Step") == "load":
            what = list(self.labels)
            random.shuffle(what)
            names = {w: f"f{random.randrange(10**6)}" for w in what}
            load_id = f"L{len(self.loads)}"
            self.loads[load_id] = names
            body = {"id": load_id, "fields": [{"label": self.labels[w], "name": names[w], "kind": self.kinds[w]}
                                              for w in what] + self.extra,
                    "consent": {"name": "c_" + load_id, "value": "necessary"}}
            if self.sum:
                body["answer"] = {"name": "ans", "image": "data:image/png;base64,AAAA"}
            return httpx.Response(200, json=body)
        load_id = request.headers.get("X-Portal-Challenge")
        names = self.loads[load_id]
        form = dict(re.findall(r'name="([^"]+)"\r\n\r\n([^\r]*)\r\n', request.content.decode()))
        sent = {w: form.get(n) for w, n in names.items()}
        self.submits.append({**sent, "consent": form.get("c_" + load_id)})
        if sent["key"] != "k":
            return httpx.Response(200, json={"error": "Invalid team key."})
        code = sent["airline"]
        total = PRICES[code] * float(sent["weight"]) / 300
        html = self.result(code, total) if self.result else (
            f'<div class="text-2xl font-semibold">EUR {total:,.2f}</div><dl><dt>Airline</dt><dd>{NAMES[code]}</dd>'
            f"<dt>Rate ID</dt><dd>R-{code}{load_id}X</dd><dt>Transit</dt><dd>3 days</dd>"
            f"<dt>Chargeable weight</dt><dd>{float(sent['weight']):g} kg</dd></dl>")
        return httpx.Response(200, json={"html": html})


def portal(fake) -> Portal:
    return Portal(base_url="https://portal.test", api_key="k", transport=httpx.MockTransport(fake))


def rate(fake, airline="GN", kg=300.0, cbm=1.2):
    p = portal(fake)
    return p, asyncio.run(p.rate("FRA", "LAX", airline, kg, cbm))


def test_the_api_is_down_and_the_form_prices_it():
    fake = FakeForm()
    p, found = rate(fake)
    assert found["total"] == 812.40 and found["rate_id"].startswith("R-GN") and found["transit_days"] == 3
    assert found["airline"] == "Gannet Airways" and found["portal_form"] and found["chargeable_weight_kg"] == 300
    sent = fake.submits[0]
    assert sent == {"origin": "FRA", "destination": "LAX", "airline": "GN", "weight": "300", "volume": "1.2", "key": "k",
                    "consent": "necessary"}
    assert "GN" not in p.down  # priced: not "down" for the memory / desk logic


def test_the_form_answer_is_cached_like_an_api_rate():
    fake = FakeForm()
    p = portal(fake)
    asyncio.run(p.rate("FRA", "LAX", "GN", 300, 1.2))
    again = asyncio.run(p.rate("FRA", "LAX", "GN", 300, 1.2))
    assert again["total"] == 812.40 and len(fake.submits) == 1


def test_a_working_api_never_touches_the_form():
    fake = FakeForm(api_status=200)

    async def handler(request):
        if request.url.host == "portal.test" and request.url.path == "/v1/portal/rates":
            return httpx.Response(200, json={"rate_id": "R-API", "airline": "Gannet Airways", "airline_code": "GN",
                                             "total": "700.00", "currency": "EUR", "transit_days": 2})
        return await fake(request)
    p = Portal(base_url="https://portal.test", api_key="k", transport=httpx.MockTransport(handler))
    assert asyncio.run(p.rate("FRA", "LAX", "GN", 300, 1.2))["rate_id"] == "R-API" and fake.submits == []


def test_a_400_from_the_api_is_no_reason_for_the_form():
    _, found = rate(FakeForm(api_status=400))
    assert found is None


def test_a_sum_is_never_solved():
    fake = FakeForm(sum_=True)
    p, found = rate(fake)
    assert found is None and fake.submits == [] and "sum" in p.last_error and "503" in p.last_error


def test_after_a_refusal_the_form_is_not_asked_again_at_once():
    fake = FakeForm(sum_=True)
    p = portal(fake)
    asyncio.run(p.rate("FRA", "LAX", "GN", 300, 1.2))
    asyncio.run(p.rate("FRA", "LAX", "MD", 300, 1.2))
    assert len(fake.loads) == 1


@pytest.mark.parametrize("labels", [
    {"origin": "Abflughafen", "destination": "Zielflughafen", "airline": "Fluggesellschaft", "weight": "Gewicht",
     "volume": "Volumen", "key": "API-Schlüssel"},
    {"origin": "From", "destination": "To", "airline": "Carrier", "weight": "Gross kg", "volume": "m³", "key": "Key"},
    {"origin": "Departure", "destination": "Arrival", "airline": "Airline code", "weight": "Actual weight",
     "volume": "Cubic metres (vol)", "key": "Password"},
])
def test_a_changed_layout_is_filled_by_kind_and_label(labels):
    fake = FakeForm(labels=labels)
    _, found = rate(fake)
    assert found and found["total"] == 812.40
    assert fake.submits[0]["origin"] == "FRA" and fake.submits[0]["destination"] == "LAX"


@pytest.mark.parametrize("labels, kinds, extra, why", [
    ({**LABELS, "origin": "Airport 1", "destination": "Airport 2"}, None, None, "label not clear"),
    ({**LABELS, "volume": "Weight / volume"}, None, None, "label not clear"),
    (None, {**KINDS, "volume": "select"}, None, "unknown form field kind"),
    (None, None, [{"label": "Email", "name": "e1", "kind": "email"}], "unknown form field kind"),
    (None, None, [{"label": "Origin (again)", "name": "o2", "kind": "airport"}], "two form fields"),
])
def test_anything_unclear_is_never_guessed(labels, kinds, extra, why):
    fake = FakeForm(labels=labels, kinds=kinds, extra=extra)
    p, found = rate(fake)
    assert found is None and fake.submits == [] and why in p.last_error


def test_slow_form_gives_up_within_its_budget(monkeypatch):
    monkeypatch.setattr(portal_form, "TIMEOUT_S", 0.2)
    p, found = rate(FakeForm(delay=1.0))
    assert found is None and "web form" in p.last_error


def test_several_airlines_each_get_their_own_form_rate_one_at_a_time():
    fake = FakeForm()
    p = portal(fake)

    async def all_three():
        return await asyncio.gather(*(p.rate("FRA", "LAX", c, 300, 1.2) for c in ("GN", "MD", "AU")))
    found = asyncio.run(all_three())
    assert [r["total"] for r in found] == [812.40, 765.10, 901.00]
    assert [s["airline"] for s in fake.submits] == ["GN", "MD", "AU"] or len(fake.submits) == 3
    assert len({r["rate_id"] for r in found}) == 3


def test_the_pricer_quotes_the_form_rates_while_the_api_is_down():
    p = portal(FakeForm())
    result = asyncio.run(Pricer(TARIFFS, Zones(), p).price(rfq("FRA", "LAX", 300, 1.2), []))
    portal_options = [o for o in result["options"] if o["source"] == "portal"]
    assert {o["airline_code"] for o in portal_options} >= {"GN", "MD"}
    assert all(o["rate_id"] for o in portal_options)


@pytest.mark.parametrize("html, total, currency, days, rate_id", [
    ("<p>Total: EUR 1,284.50</p><p>Rate ID R-GN7731A</p><p>Transit 4 days</p>", 1284.50, "EUR", 4, "R-GN7731A"),
    ("<div>€ 912,40</div><span>R-MD-22</span>", 912.40, "EUR", None, "R-MD-22"),
    ("<p>All-in price USD 1,020.00 · 2 days · R-AU9</p>", 1020.0, "USD", 2, "R-AU9"),
])
def test_result_layouts(html, total, currency, days, rate_id):
    found = portal_form.rate_from(html, "FRA", "LAX", "GN", 300)
    assert (found["total"], found["currency"], found["transit_days"], found["rate_id"]) == (total, currency, days, rate_id)


def test_an_implausible_or_empty_result_is_no_rate():
    with pytest.raises(portal_form.FormError):
        portal_form.rate_from("<p>Total EUR 3.00</p>", "FRA", "LAX", "GN", 300)  # 0.01 EUR/kg: a misread
    with pytest.raises(portal_form.FormError):
        portal_form.rate_from("<p>Please try again later.</p>", "FRA", "LAX", "GN", 300)


def test_a_usd_rate_needs_a_known_exchange_rate():
    usd = lambda code, total: f"<p>Total USD {total:,.2f}</p><p>R-{code}1</p>"
    p = portal(FakeForm(result=usd))
    assert asyncio.run(p.rate("FRA", "LAX", "GN", 300, 1.2)) is None and "exchange rate" in p.last_error
    p = portal(FakeForm(result=usd))
    p.fx["USD"] = 0.92
    found = asyncio.run(p.rate("FRA", "LAX", "GN", 300, 1.2))
    assert found["currency"] == "USD" and found["fx_eur_per_usd"] == 0.92


def test_a_wrong_team_key_is_reported_not_retried_forever():
    fake = FakeForm()
    p = Portal(base_url="https://portal.test", api_key="wrong", transport=httpx.MockTransport(fake))
    assert asyncio.run(p.rate("FRA", "LAX", "GN", 300, 1.2)) is None and "Invalid team key" in p.last_error


def test_switch_off(monkeypatch):
    monkeypatch.setattr(portal_form, "ON", False)
    fake = FakeForm()
    p, found = rate(fake)
    assert found is None and fake.loads == {}


def test_values_never_include_an_answer_field():
    load = {"id": "x", "fields": [{"label": LABELS[w], "name": w, "kind": KINDS[w]} for w in LABELS],
            "consent": {"name": "c", "value": "v"}}
    form = portal_form.values(load, "FRA", "LAX", "GN", 300, 1.2, "k")
    assert form == {"origin": "FRA", "destination": "LAX", "airline": "GN", "weight": "300", "volume": "1.2", "key": "k",
                    "c": "v"}
    with pytest.raises(portal_form.FormError, match="sum"):
        portal_form.values({**load, "answer": {"name": "a", "image": "data:"}}, "FRA", "LAX", "GN", 300, 1.2, "k")
    with pytest.raises(portal_form.FormError, match="sum"):  # a challenge under any other key: never answered either
        portal_form.values({**load, "captcha": {"image": "data:"}}, "FRA", "LAX", "GN", 300, 1.2, "k")


def test_one_fallback_the_form_stays_off_while_the_agents_portal_web_prototype_is_on(monkeypatch):
    import importlib
    monkeypatch.setenv("PORTAL_WEB", "on")
    try:
        assert importlib.reload(portal_form).ON is False
    finally:
        monkeypatch.delenv("PORTAL_WEB")
        importlib.reload(portal_form)
    assert portal_form.ON is True


def test_next_break_checks_never_use_the_form():
    fake = FakeForm()
    p = portal(fake)
    assert asyncio.run(p.rate("FRA", "LAX", "GN", 500, 1.2, optional=True)) is None and fake.loads == {}


def test_form_rates_are_marked_in_the_option_and_the_why():
    p = portal(FakeForm())
    result = asyncio.run(Pricer(TARIFFS, Zones(), p).price(rfq("FRA", "LAX", 300, 1.2), []))
    form = [o for o in result["options"] if o["source"] == "portal"]
    assert form and all(o["portal_form"] for o in form) and "PORTAL WEB FORM rates" in result["why"]
