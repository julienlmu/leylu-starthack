"""PORTAL_FORM (default on; off = the API only): the rate from 5U's portal web form when the rate API fails.

Since R93 the rate API answers 503 for hours while start-hack.5u.ai/portal/ui still prices. The page is a small app on
two POSTs to its own path (seen in the page source, /mnt/project-files/portal_ui.html):
- `X-Portal-Step: load` → {id, fields: [{label, name, kind: airport|airline|number|password}], consent: {name, value},
  answer?: {name, image}}. Field names and order change on every load; the labels and kinds stay readable.
- `X-Portal-Challenge: <id>` with the form fields (multipart) + the consent choice → {html: "<the rate>"} or {error}.
The ad pop-ups and the cookie wall exist only in the browser page; over HTTP we send the consent value the page
itself sends after "Necessary only".

What this module never does: solve a sum or captcha. A load that carries a sum (`answer` with an image) is left to a
person (PORTAL_PROBE pushes the prefilled link at T+0); no field is ever guessed: a field whose kind or label we can't
map, two fields for the same value, a missing team-key field → no submit. The result is read by rules
(portal_paste.parse: rate ID, total, currency, transit days) and checked like a pasted rate (lane, EUR/kg, days).
"""

import asyncio
import os
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

# ONE fallback per RFQ: with the agent's PORTAL_WEB prototype (#250) switched on (same root .env), this one stays off
ON = os.environ.get("PORTAL_FORM", "on").lower() != "off" and os.environ.get("PORTAL_WEB", "off").lower() != "on"
CHALLENGE = re.compile(r"captcha|challenge|answer|sum|puzzle|turnstile|recaptcha|hcaptcha", re.I)
URL = os.environ.get("PORTAL_FORM_URL", "https://start-hack.5u.ai/portal/ui")
TIMEOUT_S = float(os.environ.get("PORTAL_FORM_TIMEOUT_S", "10"))  # one airline: page, load and submit together
RETRY_S = float(os.environ.get("PORTAL_FORM_RETRY_S", "20"))  # after the form refused as a whole
FORM_LEVEL = re.compile(r"sum|field|load|layout|team key|without JSON")
VALID_S = 8 * 60  # the form shows no validity: cached like an API rate (rate IDs live about 10 minutes)
ORIGIN = re.compile(r"orig|from|depart|abflug|abgang|départ|origen|partenza|\bvon\b", re.I)
DESTINATION = re.compile(r"dest|\bto\b|arriv|ziel|nach|arrivée|destino|arrivo", re.I)
WEIGHT = re.compile(r"weight|\bkg\b|gewicht|poids|peso|mass", re.I)
VOLUME = re.compile(r"vol|cbm|\bm3\b|m³|cubic", re.I)
CHARGEABLE = re.compile(r"(?:chargeable|billed|billable|abrechnungs)\D{0,30}?(\d[\d.,']*)\s*kg", re.I)
VALID_UNTIL = re.compile(r"(?:valid|gültig)\D{0,20}(20\d\d-\d\d-\d\dT[\d:]+(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?)", re.I)


class FormError(Exception):
    """The form can't be filled without guessing or solving (the reason is shown in the session)."""


def _fields(load: dict) -> list[dict]:
    fields = load.get("fields") or load.get("inputs")
    if not isinstance(fields, list) or not fields:
        raise FormError("the form's load has no field list")
    return fields


def values(load: dict, origin: str, destination: str, airline: str, weight_kg: float, volume_cbm: float,
           team_key: str) -> dict[str, str]:
    """{field name: value} for this load, by each field's kind and label. FormError when anything is unclear."""
    answer = load.get("answer")
    if (isinstance(answer, dict) and (answer.get("image") or answer.get("name"))) or any(
            CHALLENGE.search(k) and v for k, v in load.items() if k != "answer"):
        raise FormError("the form asks for a sum: a person solves it (we never do)")
    out, used = {}, set()
    for field in _fields(load):
        kind, label, name = str(field.get("kind") or "").lower(), str(field.get("label") or ""), field.get("name")
        if not name:
            raise FormError(f"form field without a name ({label or kind})")
        if kind == "password":
            what, value = "key", team_key
        elif kind == "airline":
            what, value = "airline", airline
        elif kind == "airport":
            is_origin, is_destination = bool(ORIGIN.search(label)), bool(DESTINATION.search(label))
            if is_origin == is_destination:
                raise FormError(f"airport field label not clear: {label!r}")
            what, value = ("origin", origin) if is_origin else ("destination", destination)
        elif kind == "number":
            is_weight, is_volume = bool(WEIGHT.search(label)), bool(VOLUME.search(label))
            if is_weight == is_volume:
                raise FormError(f"number field label not clear: {label!r}")
            what, value = ("weight", f"{weight_kg:g}") if is_weight else ("volume", f"{volume_cbm:g}")
        else:
            raise FormError(f"unknown form field kind {kind!r} ({label!r})")
        if what in used:
            raise FormError(f"two form fields for the {what}")
        used.add(what)
        out[str(name)] = value
    if missing := {"key", "airline", "origin", "destination", "weight"} - used:
        raise FormError(f"the form has no field for: {', '.join(sorted(missing))}")
    if not team_key:
        raise FormError("no team key for the form")
    consent = load.get("consent")
    if isinstance(consent, dict) and consent.get("name"):
        out[str(consent["name"])] = str(consent.get("value") or "")
    return out


def rate_from(html: str, origin: str, destination: str, code: str, weight_kg: float) -> dict:
    """The form's result as an API-shaped rate dict (pricing.portal_option and booking read it like any other)."""
    import portal_paste  # here: portal_paste → pricing → portal → this module
    bid = portal_paste.parse(html, code)
    if bid is None:
        raise FormError("no amount in the form's result")
    if bid["currency"] not in ("EUR", "USD"):
        raise FormError(f"form result in {bid['currency']}")
    per_kg = bid["total"] / weight_kg if weight_kg else 0
    if not 0 < bid["total"] <= portal_paste.MAX_TOTAL or (weight_kg and not portal_paste.PER_KG[0] <= per_kg
                                                          <= portal_paste.PER_KG[1]):
        raise FormError(f"form total {bid['total']:,.2f} is implausible for {weight_kg:g} kg")
    if bid["transit_days"] is not None and not 0 < bid["transit_days"] <= portal_paste.MAX_DAYS:
        bid["transit_days"] = None
    text = re.sub(r"<[^>]+>", " ", html or "")
    chargeable = CHARGEABLE.search(text)
    valid = VALID_UNTIL.search(text)
    return {"rate_id": bid["rate_id"], "airline": bid["carrier"], "airline_code": code, "origin": origin,
            "destination": destination, "total": bid["total"], "currency": bid["currency"],
            "transit_days": bid["transit_days"],
            "chargeable_weight_kg": portal_paste.number(chargeable.group(1)) if chargeable else None,
            "valid_until": valid.group(1) if valid else
            (datetime.now(timezone.utc) + timedelta(seconds=VALID_S)).isoformat(), "portal_form": True}


class Form:
    """One web-form lookup at a time (a person's pace, not a crawler's); the page's cookies are kept."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, url: str | None = None):
        self.url = url or URL
        self.transport = transport
        self.lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None
        self.last: dict[str, float] = {}
        self.failed: tuple[float, str] | None = None  # the form refused (a sum, a new layout): not asked again at once

    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=TIMEOUT_S, transport=self.transport, follow_redirects=True,
                                           headers={"User-Agent": "Mozilla/5.0 (Leylu forwarder)"})
        return self._http

    async def rate(self, origin: str, destination: str, airline: str, weight_kg: float, volume_cbm: float,
                   team_key: str, fx: dict | None = None) -> dict:
        """The airline's rate from the web form, or FormError(why)."""
        if self.failed and time.time() - self.failed[0] < RETRY_S:
            raise FormError(f"{self.failed[1]} (not asked again for {RETRY_S:.0f} s)")
        async with self.lock:
            try:
                return await asyncio.wait_for(self._rate(origin, destination, airline, weight_kg, volume_cbm, team_key,
                                                         fx), TIMEOUT_S)
            except FormError as error:
                if FORM_LEVEL.search(str(error)):  # the form itself, not this airline's answer
                    self.failed = (time.time(), str(error))
                raise

    async def _rate(self, origin, destination, airline, weight_kg, volume_cbm, team_key, fx) -> dict:
        http = self.http()
        if not http.cookies:
            await http.get(self.url)  # the page itself first, as a browser does (its cookies, if any)
        load = await http.post(self.url, headers={"X-Portal-Step": "load"})
        try:
            data = load.json()
        except ValueError:
            raise FormError(f"form load answered {load.status_code} without JSON")
        if load.status_code != 200 or not isinstance(data, dict) or not data.get("id"):
            raise FormError(f"form load {load.status_code}: {str(data.get('error') if isinstance(data, dict) else data)[:200]}")
        form = values(data, origin, destination, airline, weight_kg, volume_cbm, team_key)
        sent = await http.post(self.url, headers={"X-Portal-Challenge": str(data["id"])},
                               files={k: (None, v) for k, v in form.items()})
        try:
            result = sent.json()
        except ValueError:
            raise FormError(f"form answered {sent.status_code} without JSON")
        if not isinstance(result, dict) or not result.get("html"):
            raise FormError(f"form: {str((result or {}).get('error') if isinstance(result, dict) else result)[:300]}")
        rate = rate_from(result["html"], origin, destination, airline, weight_kg)
        if rate["currency"] != "EUR":
            if not (fx or {}).get(rate["currency"]):
                raise FormError(f"form rate in {rate['currency']} and no exchange rate known yet")
            rate["fx_eur_per_usd"] = fx[rate["currency"]]
        self.last[airline] = time.time()
        return rate
